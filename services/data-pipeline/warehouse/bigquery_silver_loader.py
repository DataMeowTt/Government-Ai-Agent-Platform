from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from warehouse.bigquery_silver_load_plan import (
    ALLOWED_SOURCES,
    REQUIRED_COLUMNS,
    TARGET_DATASET,
    TARGET_LOCATION,
    TARGET_PROJECT_ID,
    TARGET_TABLE,
    TARGET_TABLE_ID,
)


DEFAULT_LOAD_PLAN = "../../tmp/bigquery_silver_load_plan/load_plan.json"
DEFAULT_OUTPUT_DIR = "../../tmp/bigquery_silver_load"
DEFAULT_APPROVAL_ENV = "BIGQUERY_WRITE_APPROVED"
DEFAULT_WRITE_DISPOSITION = "WRITE_TRUNCATE"
DEFAULT_MAX_VALIDATION_BYTES = 100_000_000
EXPECTED_PLAN_VALUES = {
    "dry_run": True,
    "bigquery_write_approved": False,
    "job_started": False,
    "table_id": TARGET_TABLE_ID,
    "project_id": TARGET_PROJECT_ID,
    "dataset": TARGET_DATASET,
    "table": TARGET_TABLE,
    "location": TARGET_LOCATION,
}
DUPLICATE_KEY_COLUMNS = ("country_code", "year", "indicator", "source")
STAGING_RE = re.compile(r"^[A-Za-z0-9_]+$")


class LoadBlockedError(RuntimeError):
    pass


class _CliField:
    def __init__(self, name: str) -> None:
        self.name = name


class _CliTable:
    def __init__(
        self,
        *,
        rows: int,
        columns: list[str],
        range_partitioning: Any | None,
        clustering_fields: list[str] | None,
    ) -> None:
        self.num_rows = rows
        self.schema = [_CliField(column) for column in columns]
        self.range_partitioning = range_partitioning
        self.clustering_fields = clustering_fields


class _CliJob:
    def __init__(self, job_id: str, rows: list[tuple[Any, ...]] | None = None) -> None:
        self.job_id = job_id
        self._rows = rows or []

    def result(self) -> list[tuple[Any, ...]]:
        return self._rows


class _BqCliClient:
    backend = "bq_cli"

    def __init__(self, *, project_id: str, location: str) -> None:
        self.project_id = project_id
        self.location = location
        executable = shutil.which("bq.cmd") or shutil.which("bq")
        if not executable:
            raise RuntimeError("Unable to find bq executable on PATH.")
        self.executable = executable
        self._counter = 0

    def _job_id(self, prefix: str) -> str:
        self._counter += 1
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"{prefix}_{stamp}_{self._counter}"

    def _run(self, args: list[str], *, job_id: str | None = None, json_output: bool = False) -> Any:
        command = [
            self.executable,
            "--quiet=true",
            f"--location={self.location}",
        ]
        if json_output:
            command.append("--format=json")
        if job_id:
            command.append(f"--job_id={job_id}")
        command.extend(args)
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(
                "bq command failed: "
                f"args={args!r} stdout={result.stdout.strip()!r} stderr={result.stderr.strip()!r}"
            )
        output = result.stdout.strip()
        if json_output and output:
            return json.loads(output)
        return output

    @staticmethod
    def _bq_table_id(table_id: str) -> str:
        project_id, dataset, table = table_id.split(".", 2)
        return f"{project_id}:{dataset}.{table}"

    @staticmethod
    def _range_partitioning(payload: dict[str, Any]) -> Any | None:
        raw = payload.get("rangePartitioning")
        if not raw:
            return None
        from google.cloud import bigquery

        raw_range = raw.get("range") or {}
        return bigquery.RangePartitioning(
            field=str(raw["field"]),
            range_=bigquery.PartitionRange(
                start=int(raw_range["start"]),
                end=int(raw_range["end"]),
                interval=int(raw_range["interval"]),
            ),
        )

    def get_table(self, table_id: str) -> _CliTable:
        payload = self._run(
            ["show", self._bq_table_id(table_id)],
            json_output=True,
        )
        fields = (payload.get("schema") or {}).get("fields") or []
        clustering = payload.get("clustering") or {}
        return _CliTable(
            rows=int(payload.get("numRows") or 0),
            columns=[str(field["name"]) for field in fields],
            range_partitioning=self._range_partitioning(payload),
            clustering_fields=[str(item) for item in clustering.get("fields") or []] or None,
        )

    @staticmethod
    def _write_disposition(job_config: Any) -> str:
        return str(getattr(job_config, "write_disposition", "") or "")

    @staticmethod
    def _range_flag(job_config: Any) -> str | None:
        partitioning = getattr(job_config, "range_partitioning", None)
        if partitioning is None:
            return None
        range_ = partitioning.range_
        return f"{partitioning.field},{range_.start},{range_.end},{range_.interval}"

    @staticmethod
    def _cluster_flag(job_config: Any) -> str | None:
        fields = getattr(job_config, "clustering_fields", None)
        if not fields:
            return None
        return ",".join(str(item) for item in fields)

    def load_table_from_file(self, file_obj: Any, table_id: str, *, job_config: Any, location: str) -> _CliJob:
        if location != self.location:
            raise ValueError(f"Location mismatch: client={self.location!r} request={location!r}")
        job_id = self._job_id("silver_load")
        args = ["load", "--source_format=PARQUET"]
        if self._write_disposition(job_config) == "WRITE_TRUNCATE":
            args.append("--replace=true")
            range_flag = self._range_flag(job_config)
            if range_flag:
                args.append(f"--range_partitioning={range_flag}")
            cluster_flag = self._cluster_flag(job_config)
            if cluster_flag:
                args.append(f"--clustering_fields={cluster_flag}")
        args.extend([self._bq_table_id(table_id), str(file_obj.name)])
        self._run(args, job_id=job_id)
        return _CliJob(job_id)

    def copy_table(self, source: str, destination: str, *, job_config: Any, location: str) -> _CliJob:
        del job_config
        if location != self.location:
            raise ValueError(f"Location mismatch: client={self.location!r} request={location!r}")
        job_id = self._job_id("silver_copy")
        self._run(
            ["cp", "--force=true", self._bq_table_id(source), self._bq_table_id(destination)],
            job_id=job_id,
        )
        return _CliJob(job_id)

    def query(self, query: str, *, job_config: Any, location: str) -> _CliJob:
        if location != self.location:
            raise ValueError(f"Location mismatch: client={self.location!r} request={location!r}")
        job_id = self._job_id("silver_query")
        max_bytes = int(getattr(job_config, "maximum_bytes_billed", 0) or 0)
        args = ["query", "--nouse_legacy_sql"]
        if max_bytes:
            args.append(f"--maximum_bytes_billed={max_bytes}")
        args.append(query)
        payload = self._run(args, job_id=job_id, json_output=True)
        rows: list[tuple[Any, ...]] = []
        for row in payload or []:
            if "row_count" in row and "source" in row:
                rows.append((row["source"], int(row["row_count"])))
            elif "f0_" in row:
                rows.append((int(row["f0_"]),))
            else:
                values = list(row.values())
                rows.append(tuple(values))
        return _CliJob(job_id, rows)


@dataclass(frozen=True)
class LocalValidation:
    row_count: int
    actual_columns: list[str]
    missing_columns: list[str]
    duplicate_key_count: int
    observed_sources: list[str]
    source_counts: dict[str, int]
    matches_plan_row_count: bool
    matches_plan_source_counts: bool


def _resolve_path(raw_path: str | Path) -> Path:
    return Path(raw_path).expanduser().resolve()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _data_files(path: Path, source_format: str) -> list[Path]:
    suffix = f".{source_format.lower()}"
    if path.is_file():
        return [path] if path.suffix.lower() == suffix else []
    if not path.exists():
        return []
    return sorted(
        item
        for item in path.rglob("*")
        if item.is_file() and item.suffix.lower() == suffix and not item.name.startswith(".")
    )


def _load_local_frame(path: Path, source_format: str) -> pd.DataFrame:
    if source_format == "parquet":
        import pyarrow.dataset as ds

        return ds.dataset(str(path), format="parquet").to_table().to_pandas()
    if source_format == "csv":
        files = _data_files(path, source_format)
        if not files:
            raise FileNotFoundError(f"No CSV files found for local Silver input: {path}")
        frames = [pd.read_csv(item, encoding="utf-8") for item in files]
        return pd.concat(frames, ignore_index=True)
    raise ValueError(f"Unsupported source_format: {source_format!r}")


def load_plan(path: str | Path) -> dict[str, Any]:
    plan_path = _resolve_path(path)
    if not plan_path.exists():
        raise FileNotFoundError(f"Load plan not found: {plan_path}")
    return _read_json(plan_path)


def validate_load_plan(plan: dict[str, Any]) -> None:
    mismatches = {
        key: {"expected": expected, "actual": plan.get(key)}
        for key, expected in EXPECTED_PLAN_VALUES.items()
        if plan.get(key) != expected
    }
    if mismatches:
        raise ValueError(f"Load plan failed required checks: {mismatches}")


def validate_target_args(*, project_id: str, dataset: str, table: str, location: str) -> str:
    table_id = f"{project_id}.{dataset}.{table}"
    if table_id != TARGET_TABLE_ID:
        raise ValueError(f"Target table identity must be exact: expected={TARGET_TABLE_ID!r} actual={table_id!r}")
    if location != TARGET_LOCATION:
        raise ValueError(f"Target location must be exact: expected={TARGET_LOCATION!r} actual={location!r}")
    return table_id


def validate_local_input(plan: dict[str, Any]) -> LocalValidation:
    local_path = _resolve_path(str(plan["local_silver_path"]))
    source_format = str(plan["source_format"]).strip().lower()
    files = _data_files(local_path, source_format)
    if not files:
        raise FileNotFoundError(f"No local Silver {source_format} files found: {local_path}")

    frame = _load_local_frame(local_path, source_format)
    if frame.empty:
        raise ValueError(f"Local Silver input is empty: {local_path}")

    actual_columns = list(frame.columns)
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in actual_columns]
    if missing_columns:
        raise ValueError(f"Local Silver input is missing required columns: {missing_columns}")

    observed_sources = sorted(str(value) for value in frame["source"].dropna().astype(str).unique().tolist())
    if "fao_macro" in observed_sources:
        raise ValueError("Local Silver contains source='fao_macro'; expected normalized source value 'macro'.")

    invalid_sources = sorted(set(observed_sources) - set(ALLOWED_SOURCES))
    if invalid_sources:
        raise ValueError(f"Local Silver contains invalid source values: {invalid_sources}")

    duplicate_key_count = int(frame.duplicated(subset=list(DUPLICATE_KEY_COLUMNS)).sum())
    if duplicate_key_count:
        raise ValueError(f"Local Silver duplicate key count is not zero: {duplicate_key_count}")

    source_counts = {str(key): int(value) for key, value in frame.groupby("source").size().to_dict().items()}
    row_count = int(len(frame))
    plan_source_counts = {str(key): int(value) for key, value in (plan.get("source_counts") or {}).items()}

    if row_count != int(plan["row_count"]):
        raise ValueError(f"Local row_count does not match plan: local={row_count} plan={plan['row_count']}")
    if plan_source_counts and source_counts != plan_source_counts:
        raise ValueError(f"Local source_counts do not match plan: local={source_counts!r} plan={plan_source_counts!r}")

    return LocalValidation(
        row_count=row_count,
        actual_columns=actual_columns,
        missing_columns=missing_columns,
        duplicate_key_count=duplicate_key_count,
        observed_sources=observed_sources,
        source_counts=source_counts,
        matches_plan_row_count=True,
        matches_plan_source_counts=not plan_source_counts or source_counts == plan_source_counts,
    )


def build_command_preview(
    *,
    load_plan_path: str,
    project_id: str,
    dataset: str,
    table: str,
    location: str,
    output_dir: str,
    approval_env: str,
    write_disposition: str,
    max_validation_bytes: int,
) -> str:
    return (
        f"$env:{approval_env}='true'; "
        "python -m jobs.load_silver_bigquery "
        f"--load-plan {load_plan_path} "
        f"--project-id {project_id} "
        f"--dataset {dataset} "
        f"--table {table} "
        f"--location {location} "
        f"--output-dir {output_dir} "
        f"--write-disposition {write_disposition} "
        f"--max-validation-bytes {max_validation_bytes}"
    )


def write_command_preview(output_dir: str | Path, command: str) -> Path:
    target = _resolve_path(output_dir) / "load_command_preview.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(command + "\n", encoding="utf-8")
    return target


def require_approval(env_name: str) -> str:
    value = os.environ.get(env_name)
    if value != "true":
        raise LoadBlockedError(f"{env_name} must be exactly true before BigQuery write; observed={value!r}")
    return value


def get_active_gcloud_project() -> str:
    executable = shutil.which("gcloud.cmd") or shutil.which("gcloud")
    if not executable:
        raise RuntimeError("Unable to find gcloud executable on PATH.")
    result = subprocess.run(
        [executable, "config", "get-value", "project"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Unable to read active gcloud project: {result.stderr.strip()}")
    return result.stdout.strip()


def require_active_project(project_id: str, getter: Callable[[], str] = get_active_gcloud_project) -> str:
    active_project = getter()
    if active_project != project_id:
        raise RuntimeError(f"Active gcloud project mismatch: expected={project_id!r} actual={active_project!r}")
    return active_project


def _make_client(project_id: str, location: str) -> Any:
    from google.cloud import bigquery

    try:
        return bigquery.Client(project=project_id, location=location)
    except Exception as exc:
        if exc.__class__.__name__ != "DefaultCredentialsError":
            raise
        return _BqCliClient(project_id=project_id, location=location)


def _schema_columns(table: Any) -> list[str]:
    return [field.name for field in getattr(table, "schema", [])]


def _assert_schema_contains(table: Any, table_id: str) -> list[str]:
    columns = _schema_columns(table)
    missing = [column for column in REQUIRED_COLUMNS if column not in columns]
    if missing:
        raise ValueError(f"BigQuery table schema missing required columns: table={table_id} missing={missing}")
    return columns


def _make_staging_table_id(*, project_id: str, dataset: str, table: str, staging_table: str | None) -> str:
    if staging_table:
        candidate = staging_table.strip()
        if "." in candidate:
            parts = candidate.split(".")
            if len(parts) != 3 or parts[0] != project_id or parts[1] != dataset:
                raise ValueError(f"Staging table must stay in {project_id}.{dataset}: {staging_table!r}")
            table_name = parts[2]
        else:
            table_name = candidate
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        table_name = f"{table}_staging_run_{stamp}"

    if not STAGING_RE.fullmatch(table_name):
        raise ValueError(f"Unsafe staging table name: {table_name!r}")
    if table_name == table:
        raise ValueError("Staging table name must not equal production table name.")
    return f"{project_id}.{dataset}.{table_name}"


def _load_job_config(plan: dict[str, Any], write_disposition: str, target_table: Any | None = None) -> Any:
    from google.cloud import bigquery

    config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition=write_disposition,
        create_disposition=bigquery.CreateDisposition.CREATE_IF_NEEDED,
    )
    target_range = getattr(target_table, "range_partitioning", None)
    if target_range is not None:
        config.range_partitioning = target_range
    else:
        partition = plan.get("partition") or {}
        if partition.get("type") == "integer_range":
            config.range_partitioning = bigquery.RangePartitioning(
                field=str(partition["column"]),
                range_=bigquery.PartitionRange(
                    start=int(partition["start"]),
                    end=int(partition["end"]),
                    interval=int(partition["interval"]),
                ),
            )

    target_cluster = getattr(target_table, "clustering_fields", None)
    if target_cluster:
        config.clustering_fields = list(target_cluster)
    else:
        cluster = plan.get("cluster") or []
        if cluster:
            config.clustering_fields = [str(item) for item in cluster]
    return config


def _copy_job_config(write_disposition: str) -> Any:
    from google.cloud import bigquery

    return bigquery.CopyJobConfig(write_disposition=write_disposition)


def _query_job_config(max_validation_bytes: int) -> Any:
    from google.cloud import bigquery

    return bigquery.QueryJobConfig(maximum_bytes_billed=max_validation_bytes, use_legacy_sql=False)


def _query_scalar(client: Any, query: str, *, location: str, max_validation_bytes: int) -> tuple[int, str]:
    job = client.query(query, job_config=_query_job_config(max_validation_bytes), location=location)
    rows = list(job.result())
    return int(rows[0][0]), job.job_id


def _query_source_counts(
    client: Any,
    table_id: str,
    *,
    location: str,
    max_validation_bytes: int,
) -> tuple[dict[str, int] | None, str | None, str | None]:
    query = f"SELECT source, COUNT(*) AS row_count FROM `{table_id}` GROUP BY source ORDER BY source"
    try:
        job = client.query(query, job_config=_query_job_config(max_validation_bytes), location=location)
        rows = list(job.result())
        return {str(row[0]): int(row[1]) for row in rows}, job.job_id, None
    except Exception as exc:  # pragma: no cover - fallback depends on BigQuery cost estimation.
        sample_query = (
            f"SELECT source, COUNT(*) AS row_count FROM "
            f"(SELECT source FROM `{table_id}` LIMIT 10000) GROUP BY source ORDER BY source"
        )
        job = client.query(sample_query, job_config=_query_job_config(max_validation_bytes), location=location)
        rows = list(job.result())
        return {str(row[0]): int(row[1]) for row in rows}, job.job_id, str(exc)


def execute_silver_load(
    *,
    plan: dict[str, Any],
    load_plan_path: str,
    project_id: str,
    dataset: str,
    table: str,
    location: str,
    approval_env: str,
    output_dir: str | Path,
    staging_table: str | None = None,
    write_disposition: str = DEFAULT_WRITE_DISPOSITION,
    max_validation_bytes: int = DEFAULT_MAX_VALIDATION_BYTES,
    client_factory: Callable[[str, str], Any] = _make_client,
    active_project_getter: Callable[[], str] = get_active_gcloud_project,
) -> dict[str, Any]:
    validate_load_plan(plan)
    target_table_id = validate_target_args(project_id=project_id, dataset=dataset, table=table, location=location)
    if write_disposition != DEFAULT_WRITE_DISPOSITION:
        raise ValueError(f"Only {DEFAULT_WRITE_DISPOSITION} is allowed for this load.")

    command = build_command_preview(
        load_plan_path=load_plan_path,
        project_id=project_id,
        dataset=dataset,
        table=table,
        location=location,
        output_dir=str(output_dir),
        approval_env=approval_env,
        write_disposition=write_disposition,
        max_validation_bytes=max_validation_bytes,
    )
    preview_path = write_command_preview(output_dir, command)

    local_validation = validate_local_input(plan)
    approval_value = require_approval(approval_env)
    active_project = require_active_project(project_id, active_project_getter)

    client = client_factory(project_id, location)
    target_before = client.get_table(target_table_id)
    target_schema_before = _assert_schema_contains(target_before, target_table_id)
    target_rows_before = int(getattr(target_before, "num_rows", 0))

    source_format = str(plan["source_format"]).strip().lower()
    if source_format != "parquet":
        raise ValueError(f"Only parquet BigQuery loads are enabled for this approved run: {source_format!r}")

    files = _data_files(_resolve_path(str(plan["local_silver_path"])), source_format)
    staging_table_id = _make_staging_table_id(
        project_id=project_id,
        dataset=dataset,
        table=table,
        staging_table=staging_table,
    )

    load_job_ids: list[str] = []
    for index, file_path in enumerate(files):
        disposition = DEFAULT_WRITE_DISPOSITION if index == 0 else "WRITE_APPEND"
        job_config = _load_job_config(plan, disposition, target_before)
        with file_path.open("rb") as file_obj:
            job = client.load_table_from_file(file_obj, staging_table_id, job_config=job_config, location=location)
            job.result()
        load_job_ids.append(str(job.job_id))

    staging_table_obj = client.get_table(staging_table_id)
    staging_schema = _assert_schema_contains(staging_table_obj, staging_table_id)
    staging_row_count, staging_count_job_id = _query_scalar(
        client,
        f"SELECT COUNT(*) FROM `{staging_table_id}`",
        location=location,
        max_validation_bytes=max_validation_bytes,
    )
    if staging_row_count != local_validation.row_count:
        raise ValueError(
            f"Staging row_count mismatch: staging={staging_row_count} expected={local_validation.row_count}"
        )

    copy_job = client.copy_table(
        staging_table_id,
        target_table_id,
        job_config=_copy_job_config(write_disposition),
        location=location,
    )
    copy_job.result()

    target_after = client.get_table(target_table_id)
    target_schema_after = _assert_schema_contains(target_after, target_table_id)
    target_row_count, target_count_job_id = _query_scalar(
        client,
        f"SELECT COUNT(*) FROM `{target_table_id}`",
        location=location,
        max_validation_bytes=max_validation_bytes,
    )
    if target_row_count != local_validation.row_count:
        raise ValueError(f"Target row_count mismatch: target={target_row_count} expected={local_validation.row_count}")

    observed_source_counts, source_counts_job_id, source_counts_fallback_reason = _query_source_counts(
        client,
        target_table_id,
        location=location,
        max_validation_bytes=max_validation_bytes,
    )
    source_counts_match = observed_source_counts == local_validation.source_counts
    if observed_source_counts is not None and source_counts_fallback_reason is None and not source_counts_match:
        raise ValueError(
            f"Target source_counts mismatch: target={observed_source_counts!r} expected={local_validation.source_counts!r}"
        )

    result = {
        "approval_env": approval_env,
        "approval_value": approval_value,
        "active_project": active_project,
        "bigquery_backend": getattr(client, "backend", "python_client"),
        "load_plan_path": str(_resolve_path(load_plan_path)),
        "local_silver_path": str(_resolve_path(str(plan["local_silver_path"]))),
        "local_manifest_path": str(_resolve_path(str(plan["local_manifest_path"]))),
        "target_table_id": target_table_id,
        "staging_table_used": True,
        "staging_table_id": staging_table_id,
        "write_disposition": write_disposition,
        "expected_row_count": local_validation.row_count,
        "target_rows_before": target_rows_before,
        "staging_row_count": staging_row_count,
        "target_row_count_after": target_row_count,
        "load_job_ids": load_job_ids,
        "copy_job_id": str(copy_job.job_id),
        "validation_query_job_ids": {
            "staging_count": staging_count_job_id,
            "target_count": target_count_job_id,
            "source_counts": source_counts_job_id,
        },
        "command_preview_path": str(preview_path),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    validation = {
        "target_table_id": target_table_id,
        "staging_table_id": staging_table_id,
        "schema_validation": {
            "target_schema_before": target_schema_before,
            "staging_schema": staging_schema,
            "target_schema_after": target_schema_after,
            "required_columns": list(REQUIRED_COLUMNS),
            "required_columns_present": True,
        },
        "local_validation": {
            "row_count": local_validation.row_count,
            "actual_columns": local_validation.actual_columns,
            "missing_columns": local_validation.missing_columns,
            "duplicate_key_count": local_validation.duplicate_key_count,
            "observed_sources": local_validation.observed_sources,
            "source_counts": local_validation.source_counts,
            "matches_plan_row_count": local_validation.matches_plan_row_count,
            "matches_plan_source_counts": local_validation.matches_plan_source_counts,
        },
        "bigquery_validation": {
            "target_rows_before": target_rows_before,
            "staging_row_count": staging_row_count,
            "target_row_count_after": target_row_count,
            "row_count_matches_expected": target_row_count == local_validation.row_count,
            "source_counts": observed_source_counts,
            "source_counts_match_expected": source_counts_match,
            "source_counts_fallback_reason": source_counts_fallback_reason,
            "validation_query_job_ids": result["validation_query_job_ids"],
            "max_validation_bytes": max_validation_bytes,
        },
    }
    output_path = _resolve_path(output_dir)
    _write_json(output_path / "load_result.json", result)
    _write_json(output_path / "load_validation.json", validation)
    return {"result": result, "validation": validation}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load validated local Silver indicators into BigQuery.")
    parser.add_argument("--load-plan", default=DEFAULT_LOAD_PLAN)
    parser.add_argument("--project-id", default=TARGET_PROJECT_ID)
    parser.add_argument("--dataset", default=TARGET_DATASET)
    parser.add_argument("--table", default=TARGET_TABLE)
    parser.add_argument("--location", default=TARGET_LOCATION)
    parser.add_argument("--approval-env", default=DEFAULT_APPROVAL_ENV)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--staging-table", default=None)
    parser.add_argument("--write-disposition", default=DEFAULT_WRITE_DISPOSITION)
    parser.add_argument("--max-validation-bytes", type=int, default=DEFAULT_MAX_VALIDATION_BYTES)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    plan = load_plan(args.load_plan)
    try:
        payload = execute_silver_load(
            plan=plan,
            load_plan_path=args.load_plan,
            project_id=args.project_id,
            dataset=args.dataset,
            table=args.table,
            location=args.location,
            approval_env=args.approval_env,
            output_dir=args.output_dir,
            staging_table=args.staging_table,
            write_disposition=args.write_disposition,
            max_validation_bytes=args.max_validation_bytes,
        )
    except LoadBlockedError as exc:
        command = build_command_preview(
            load_plan_path=args.load_plan,
            project_id=args.project_id,
            dataset=args.dataset,
            table=args.table,
            location=args.location,
            output_dir=args.output_dir,
            approval_env=args.approval_env,
            write_disposition=args.write_disposition,
            max_validation_bytes=args.max_validation_bytes,
        )
        write_command_preview(args.output_dir, command)
        print(str(exc))
        print(f"Rerun with approval: {command}")
        return 2

    print(json.dumps(payload["result"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0
