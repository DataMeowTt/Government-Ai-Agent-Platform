from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from warehouse.bigquery_warehouse_validation import parse_table_id


DEFAULT_APPROVAL_ENV = "BIGQUERY_WAREHOUSE_WRITE_APPROVED"


@dataclass(frozen=True)
class WarehouseWriteResult:
    dataset: str
    staging_table: str
    production_table: str
    staging_table_id: str
    production_table_id: str
    write_disposition: str
    local_row_count: int
    staging_row_count: int
    production_row_count: int
    staging_columns: list[str]
    load_job_id: str
    copy_job_id: str


def require_write_approval(env_name: str = DEFAULT_APPROVAL_ENV) -> str:
    value = os.environ.get(env_name)
    if value != "true":
        raise RuntimeError(f"{env_name} must be exactly true before BigQuery write; observed={value!r}")
    return value


class BigQueryWarehouseWriter:
    def __init__(self, *, project_id: str, location: str) -> None:
        self.project_id = project_id
        self.location = location
        self.backend = "python_client"
        self._client: Any | None = None
        self._bq_executable: str | None = None
        try:
            from google.cloud import bigquery
        except Exception:
            self._activate_cli_backend()
            return
        try:
            self._client = bigquery.Client(project=project_id, location=location)
        except Exception as exc:  # pragma: no cover - depends on local ADC.
            if exc.__class__.__name__ != "DefaultCredentialsError":
                raise
            self._activate_cli_backend()

    def _activate_cli_backend(self) -> None:
        executable = shutil.which("bq.cmd") or shutil.which("bq")
        if not executable:
            raise RuntimeError("Unable to find bq executable on PATH.")
        self.backend = "bq_cli"
        self._bq_executable = executable
        self._client = None

    @staticmethod
    def _to_bq_table_ref(table_id: str) -> str:
        project, dataset, table = parse_table_id(table_id)
        return f"{project}:{dataset}.{table}"

    def _run_bq(self, args: list[str], *, job_id: str | None = None, json_output: bool = False) -> str:
        if not self._bq_executable:
            raise RuntimeError("bq executable is not configured.")
        command = [
            self._bq_executable,
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
        return result.stdout

    @staticmethod
    def _job_id(prefix: str) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        return f"{prefix}_{stamp}"

    def get_table_layout(self, table_id: str) -> tuple[dict[str, int | str] | None, list[str] | None]:
        if self.backend == "python_client":
            table_obj = self._client.get_table(table_id)
            range_partitioning = getattr(table_obj, "range_partitioning", None)
            clustering_fields = getattr(table_obj, "clustering_fields", None)
            partition_payload: dict[str, int | str] | None = None
            if range_partitioning and getattr(range_partitioning, "range_", None):
                partition_payload = {
                    "field": str(range_partitioning.field),
                    "start": int(range_partitioning.range_.start),
                    "end": int(range_partitioning.range_.end),
                    "interval": int(range_partitioning.range_.interval),
                }
            cluster_payload = [str(item) for item in clustering_fields] if clustering_fields else None
            return partition_payload, cluster_payload

        payload = json.loads(self._run_bq(["show", self._to_bq_table_ref(table_id)], json_output=True))
        partition_raw = payload.get("rangePartitioning")
        partition_payload = None
        if partition_raw:
            raw_range = partition_raw.get("range") or {}
            partition_payload = {
                "field": str(partition_raw["field"]),
                "start": int(raw_range["start"]),
                "end": int(raw_range["end"]),
                "interval": int(raw_range["interval"]),
            }
        clustering_raw = payload.get("clustering") or {}
        cluster_payload = [str(item) for item in (clustering_raw.get("fields") or [])] or None
        return partition_payload, cluster_payload

    def load_parquet(
        self,
        *,
        parquet_path: Path,
        table_id: str,
        range_partitioning: dict[str, int | str] | None = None,
        clustering_fields: list[str] | None = None,
    ) -> str:
        if self.backend == "python_client":
            from google.cloud import bigquery

            config = bigquery.LoadJobConfig(
                source_format=bigquery.SourceFormat.PARQUET,
                write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
                create_disposition=bigquery.CreateDisposition.CREATE_IF_NEEDED,
            )
            if range_partitioning:
                config.range_partitioning = bigquery.RangePartitioning(
                    field=str(range_partitioning["field"]),
                    range_=bigquery.PartitionRange(
                        start=int(range_partitioning["start"]),
                        end=int(range_partitioning["end"]),
                        interval=int(range_partitioning["interval"]),
                    ),
                )
            if clustering_fields:
                config.clustering_fields = list(clustering_fields)
            with parquet_path.open("rb") as file_obj:
                job = self._client.load_table_from_file(
                    file_obj,
                    table_id,
                    job_config=config,
                    location=self.location,
                )
            job.result()
            return str(job.job_id)

        job_id = self._job_id("warehouse_load")
        self._run_bq(
            [
                "load",
                "--source_format=PARQUET",
                "--replace=true",
                *(
                    [
                        "--range_partitioning="
                        f"{range_partitioning['field']},"
                        f"{int(range_partitioning['start'])},"
                        f"{int(range_partitioning['end'])},"
                        f"{int(range_partitioning['interval'])}"
                    ]
                    if range_partitioning
                    else []
                ),
                *(["--clustering_fields=" + ",".join(clustering_fields)] if clustering_fields else []),
                self._to_bq_table_ref(table_id),
                str(parquet_path),
            ],
            job_id=job_id,
        )
        return job_id

    def copy_table(self, *, source_table_id: str, destination_table_id: str) -> str:
        if self.backend == "python_client":
            from google.cloud import bigquery

            config = bigquery.CopyJobConfig(write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE)
            job = self._client.copy_table(
                source_table_id,
                destination_table_id,
                job_config=config,
                location=self.location,
            )
            job.result()
            return str(job.job_id)

        job_id = self._job_id("warehouse_copy")
        self._run_bq(
            [
                "cp",
                "--force=true",
                self._to_bq_table_ref(source_table_id),
                self._to_bq_table_ref(destination_table_id),
            ],
            job_id=job_id,
        )
        return job_id

    def get_table_info(self, table_id: str) -> tuple[int, list[str]]:
        if self.backend == "python_client":
            table_obj = self._client.get_table(table_id)
            return int(table_obj.num_rows), [field.name for field in table_obj.schema]

        payload = json.loads(self._run_bq(["show", self._to_bq_table_ref(table_id)], json_output=True))
        fields = ((payload.get("schema") or {}).get("fields") or [])
        return int(payload.get("numRows") or 0), [str(field["name"]) for field in fields]

    def count_rows(self, table_id: str) -> int:
        if self.backend == "python_client":
            from google.cloud import bigquery

            query = f"SELECT COUNT(*) FROM `{table_id}`"
            job = self._client.query(
                query,
                location=self.location,
                job_config=bigquery.QueryJobConfig(use_legacy_sql=False),
            )
            rows = list(job.result())
            return int(rows[0][0]) if rows else 0

        result = self._run_bq(["query", "--nouse_legacy_sql", "--format=json", f"SELECT COUNT(*) AS c FROM `{table_id}`"], json_output=True)
        payload = json.loads(result)
        if not payload:
            return 0
        return int(payload[0]["c"])


def publish_with_staging(
    *,
    project_id: str,
    location: str,
    dataset: str,
    staging_table: str,
    production_table: str,
    parquet_path: Path,
    expected_required_columns: list[str],
    local_row_count: int,
    writer: BigQueryWarehouseWriter | None = None,
) -> WarehouseWriteResult:
    active_writer = writer or BigQueryWarehouseWriter(project_id=project_id, location=location)
    staging_table_id = f"{project_id}.{dataset}.{staging_table}"
    production_table_id = f"{project_id}.{dataset}.{production_table}"
    range_partitioning, clustering_fields = active_writer.get_table_layout(production_table_id)
    load_job_id = active_writer.load_parquet(
        parquet_path=parquet_path,
        table_id=staging_table_id,
        range_partitioning=range_partitioning,
        clustering_fields=clustering_fields,
    )
    staging_row_count, staging_columns = active_writer.get_table_info(staging_table_id)
    if staging_row_count != local_row_count:
        raise ValueError(
            f"Staging row_count mismatch for {staging_table_id}: "
            f"staging={staging_row_count} local={local_row_count}"
        )
    missing_columns = [column for column in expected_required_columns if column not in staging_columns]
    if missing_columns:
        raise ValueError(f"Staging schema missing columns for {staging_table_id}: {missing_columns}")
    copy_job_id = active_writer.copy_table(
        source_table_id=staging_table_id,
        destination_table_id=production_table_id,
    )
    production_row_count = active_writer.count_rows(production_table_id)
    if production_row_count != local_row_count:
        raise ValueError(
            f"Production row_count mismatch for {production_table_id}: "
            f"production={production_row_count} local={local_row_count}"
        )
    return WarehouseWriteResult(
        dataset=dataset,
        staging_table=staging_table,
        production_table=production_table,
        staging_table_id=staging_table_id,
        production_table_id=production_table_id,
        write_disposition="WRITE_TRUNCATE",
        local_row_count=local_row_count,
        staging_row_count=staging_row_count,
        production_row_count=production_row_count,
        staging_columns=staging_columns,
        load_job_id=load_job_id,
        copy_job_id=copy_job_id,
    )


def save_write_results(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
