from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from storage.bigquery_loader import build_table_id


TARGET_PROJECT_ID = "western-pivot-452008-a6"
TARGET_DATASET = "gov_ai_silver"
TARGET_TABLE = "silver_indicators"
TARGET_LOCATION = "asia-southeast1"
TARGET_TABLE_ID = f"{TARGET_PROJECT_ID}.{TARGET_DATASET}.{TARGET_TABLE}"

REQUIRED_COLUMNS = (
    "country_code",
    "country",
    "year",
    "indicator",
    "value",
    "source",
    "run_id",
    "run_date",
    "loaded_at",
)
ALLOWED_SOURCES = {"wdi", "gmd", "macro"}
SOURCE_ALIASES = {"fao_macro": "macro"}

DEFAULT_WRITE_DISPOSITION = "WRITE_TRUNCATE"
DEFAULT_CREATE_DISPOSITION = "CREATE_NEVER"


@dataclass(frozen=True)
class SilverArtifacts:
    local_silver_path: Path
    local_manifest_path: Path
    source_format: str
    manifest: dict[str, Any]
    checked_paths: tuple[str, ...]
    detection_mode: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _contract_path(repo_root: Path) -> Path:
    return repo_root / "contracts" / "table_contract.yaml"


def _default_silver_candidates(repo_root: Path) -> list[Path]:
    return [
        repo_root / "tmp" / "silver_local_output",
        repo_root / "tmp" / "silver_fixture_output",
    ]


def _resolve_path(raw_path: str | Path, *, base_dir: Path | None = None) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = (base_dir or Path.cwd()) / path
    return path.resolve()


def _data_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]

    if not path.exists():
        return []

    files = [
        item
        for item in sorted(path.rglob("*"))
        if item.is_file()
        and item.suffix.lower() in {".csv", ".parquet"}
        and not item.name.startswith(".")
    ]
    return files


def _detect_source_format(path: Path, manifest: dict[str, Any] | None = None) -> str:
    manifest_format = str((manifest or {}).get("output_format") or "").strip().lower()
    files = _data_files(path)
    if manifest_format in {"csv", "parquet"}:
        actual_formats = {item.suffix.lower().lstrip(".") for item in files if item.suffix}
        if not actual_formats:
            raise ValueError(f"Unable to detect local Silver file format from: {path}")
        if actual_formats != {manifest_format}:
            raise ValueError(
                "Manifest output_format does not match local Silver files: "
                f"manifest={manifest_format!r} actual={sorted(actual_formats)!r}"
            )
        return manifest_format

    if any(item.suffix.lower() == ".parquet" for item in files):
        return "parquet"
    if any(item.suffix.lower() == ".csv" for item in files):
        return "csv"
    raise ValueError(f"Unable to detect source format from local Silver path: {path}")


def _manifest_output_path(manifest: dict[str, Any], manifest_path: Path) -> Path | None:
    raw_output = str(manifest.get("silver_output_path") or "").strip()
    if raw_output:
        return _resolve_path(raw_output, base_dir=manifest_path.parent)
    return None


def _candidate_output_paths(raw_path: str | Path, *, repo_root: Path) -> list[Path]:
    candidate = _resolve_path(raw_path, base_dir=Path.cwd())
    candidates = [candidate]
    if candidate.is_dir() or candidate.suffix == "":
        candidates.append(candidate / "silver_indicators")

    if candidate == repo_root / "tmp" / "silver_local_output":
        candidates.append(candidate / "silver_indicators")

    unique: list[Path] = []
    seen: set[str] = set()
    for item in candidates:
        key = str(item)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _load_manifest(manifest_path: Path) -> dict[str, Any]:
    if not manifest_path.exists():
        raise FileNotFoundError(f"Silver manifest not found: {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _select_artifacts_from_explicit_paths(
    *,
    silver_output_dir: str | None,
    silver_manifest: str | None,
    repo_root: Path,
) -> SilverArtifacts:
    checked: list[str] = []

    manifest_path: Path | None = None
    manifest: dict[str, Any] | None = None
    local_silver_path: Path | None = None

    if silver_manifest:
        manifest_path = _resolve_path(silver_manifest, base_dir=Path.cwd())
        checked.append(str(manifest_path))
        if not manifest_path.exists():
            raise FileNotFoundError(
                "No local Silver manifest found.\n"
                f"Checked:\n- {manifest_path}\n"
                "Run local Silver build again:\n"
                "cd services/data-pipeline && python -m jobs.build_silver "
                "--source all --run-id local-silver-smoke --run-date 2026-05-18 "
                "--output-dir ../../tmp/silver_local_output --output-format parquet "
                "--spark-master local[*]"
            )
        manifest = _load_manifest(manifest_path)
        output_from_manifest = _manifest_output_path(manifest, manifest_path)
        if output_from_manifest is None:
            raise ValueError(f"silver_manifest.json is missing silver_output_path: {manifest_path}")
        local_silver_path = output_from_manifest
        checked.append(str(local_silver_path))
        if not _data_files(local_silver_path):
            checked_text = "\n".join(f"- {item}" for item in checked)
            raise FileNotFoundError(
                "No local Silver output found for the provided manifest.\n"
                f"Checked:\n{checked_text}\n"
                "Run local Silver build again:\n"
                "cd services/data-pipeline && python -m jobs.build_silver "
                "--source all --run-id local-silver-smoke --run-date 2026-05-18 "
                "--output-dir ../../tmp/silver_local_output --output-format parquet "
                "--spark-master local[*]"
            )
    elif silver_output_dir:
        candidates = _candidate_output_paths(silver_output_dir, repo_root=repo_root)
        for candidate in candidates:
            checked.append(str(candidate))
            if _data_files(candidate):
                local_silver_path = candidate
                break
        if local_silver_path is None:
            checked_text = "\n".join(f"- {item}" for item in checked)
            raise FileNotFoundError(
                "No local Silver output found.\n"
                f"Checked:\n{checked_text}\n"
                "Run local Silver build again:\n"
                "cd services/data-pipeline && python -m jobs.build_silver "
                "--source all --run-id local-silver-smoke --run-date 2026-05-18 "
                "--output-dir ../../tmp/silver_local_output --output-format parquet "
                "--spark-master local[*]"
            )
        manifest_path = local_silver_path.parent / "silver_manifest.json"
        checked.append(str(manifest_path))
        manifest = _load_manifest(manifest_path)
    if silver_output_dir and manifest is not None and manifest_path is not None and local_silver_path is not None:
        manifest_output = _manifest_output_path(manifest, manifest_path)
        explicit_candidates = {
            str(candidate.resolve()) for candidate in _candidate_output_paths(silver_output_dir, repo_root=repo_root)
        }
        if str(local_silver_path.resolve()) not in explicit_candidates:
            raise ValueError(
                "Provided silver_output_dir does not match the resolved Silver output path: "
                f"output={local_silver_path!s} candidates={sorted(explicit_candidates)!r}"
            )
        if manifest_output is not None and manifest_output.resolve() != local_silver_path.resolve():
            raise ValueError(
                "Provided silver_output_dir does not match the manifest silver_output_path: "
                f"output={local_silver_path!s} manifest={manifest_output!s}"
            )

    if manifest is None or manifest_path is None or local_silver_path is None:
        raise RuntimeError("Failed to resolve Silver artifacts.")

    return SilverArtifacts(
        local_silver_path=local_silver_path,
        local_manifest_path=manifest_path,
        source_format=_detect_source_format(local_silver_path, manifest),
        manifest=manifest,
        checked_paths=tuple(checked),
        detection_mode="explicit",
    )


def _select_artifacts_from_defaults(repo_root: Path) -> SilverArtifacts:
    checked: list[str] = []

    for run_dir in _default_silver_candidates(repo_root):
        manifest_path = run_dir / "silver_manifest.json"
        local_silver_path = run_dir / "silver_indicators"
        checked.extend([str(manifest_path), str(local_silver_path)])
        if manifest_path.exists() and _data_files(local_silver_path):
            manifest = _load_manifest(manifest_path)
            return SilverArtifacts(
                local_silver_path=local_silver_path.resolve(),
                local_manifest_path=manifest_path.resolve(),
                source_format=_detect_source_format(local_silver_path, manifest),
                manifest=manifest,
                checked_paths=tuple(checked),
                detection_mode="auto",
            )

    checked_text = "\n".join(f"- {item}" for item in checked)
    raise FileNotFoundError(
        "No local Silver output/manifest could be auto-detected.\n"
        f"Checked:\n{checked_text}\n"
        "Run local Silver build again:\n"
        "cd services/data-pipeline && python -m jobs.build_silver "
        "--source all --run-id local-silver-smoke --run-date 2026-05-18 "
        "--output-dir ../../tmp/silver_local_output --output-format parquet "
        "--spark-master local[*]"
    )


def resolve_silver_artifacts(
    *,
    silver_output_dir: str | None = None,
    silver_manifest: str | None = None,
    repo_root: Path | None = None,
) -> SilverArtifacts:
    base_repo = (repo_root or _repo_root()).resolve()
    if silver_output_dir or silver_manifest:
        return _select_artifacts_from_explicit_paths(
            silver_output_dir=silver_output_dir,
            silver_manifest=silver_manifest,
            repo_root=base_repo,
        )
    return _select_artifacts_from_defaults(base_repo)


def _read_parquet_frame(path: Path) -> pd.DataFrame:
    import pyarrow.dataset as ds

    dataset = ds.dataset(str(path), format="parquet")
    return dataset.to_table().to_pandas()


def _read_csv_frame(path: Path) -> pd.DataFrame:
    if path.is_file():
        return pd.read_csv(path, encoding="utf-8")

    files = _data_files(path)
    if not files:
        raise FileNotFoundError(f"No CSV data files found under: {path}")

    frames = [pd.read_csv(file_path, encoding="utf-8") for file_path in files]
    return pd.concat(frames, ignore_index=True)


def _load_local_frame(path: Path, source_format: str) -> pd.DataFrame:
    if source_format == "parquet":
        return _read_parquet_frame(path)
    if source_format == "csv":
        return _read_csv_frame(path)
    raise ValueError(f"Unsupported source format: {source_format!r}")


def _canonical_source(value: Any) -> str:
    cleaned = str(value or "").strip()
    return SOURCE_ALIASES.get(cleaned, cleaned)


def _list_contract_columns(contract_payload: dict[str, Any]) -> list[str]:
    silver = contract_payload.get("silver", {}) or {}
    table = silver.get(TARGET_TABLE, {}) or {}
    columns = table.get("columns", {}) or {}
    return list(columns.keys())


def _load_contract(repo_root: Path) -> dict[str, Any]:
    contract_path = _contract_path(repo_root)
    if not contract_path.exists():
        raise FileNotFoundError(f"table_contract.yaml not found: {contract_path}")
    return yaml.safe_load(contract_path.read_text(encoding="utf-8")) or {}


def _normalize_counts(raw_counts: dict[Any, Any]) -> dict[str, int]:
    return {str(key): int(value) for key, value in raw_counts.items()}


def _source_counts_from_frame(df: pd.DataFrame) -> dict[str, int]:
    counts = df.groupby("source").size().to_dict()
    return _normalize_counts(counts)


def _source_counts_from_manifest(manifest: dict[str, Any]) -> dict[str, int] | None:
    validation = manifest.get("validation_summary") or {}
    raw_counts = validation.get("source_counts")
    if isinstance(raw_counts, dict) and raw_counts:
        return _normalize_counts(raw_counts)
    return None


def _expected_next_load_command(
    *,
    silver_output_path: Path,
    silver_manifest_path: Path,
    project_id: str,
    dataset: str,
    table: str,
    location: str,
    write_disposition: str,
) -> str:
    return (
        "cd services/data-pipeline && BIGQUERY_WRITE_APPROVED=true "
        "python -m jobs.load_silver_bigquery "
        f"--silver-output-dir {silver_output_path} "
        f"--silver-manifest {silver_manifest_path} "
        f"--project-id {project_id} "
        f"--dataset {dataset} "
        f"--table {table} "
        f"--location {location} "
        f"--write-disposition {write_disposition}"
    )


def _validate_columns(
    *,
    actual_columns: list[str],
    contract_columns: list[str],
) -> dict[str, Any]:
    missing_columns = [column for column in contract_columns if column not in actual_columns]
    extra_columns = [column for column in actual_columns if column not in contract_columns]

    return {
        "required_columns": list(REQUIRED_COLUMNS),
        "actual_columns": actual_columns,
        "contract_columns": contract_columns,
        "missing_columns": missing_columns,
        "extra_columns": extra_columns,
        "order_matches_contract": actual_columns == contract_columns,
        "matches_contract": not missing_columns and not extra_columns and actual_columns == contract_columns,
    }


def _validate_values(df: pd.DataFrame) -> dict[str, Any]:
    observed_sources = sorted(
        {
            str(value)
            for value in df["source"].dropna().astype(str).tolist()
        }
    )
    canonical_sources = sorted(_canonical_source(value) for value in observed_sources)
    invalid_sources = sorted(
        {
            value
            for value in observed_sources
            if _canonical_source(value) not in ALLOWED_SOURCES
        }
    )

    country_code_series = df["country_code"].astype(str)
    invalid_country_code_count = int(
        (~df["country_code"].notna() | ~country_code_series.str.fullmatch(r"[A-Z]{3}")).sum()
    )
    year_series = pd.to_numeric(df["year"], errors="coerce")
    invalid_year_count = int((year_series.isna() | ~year_series.between(1980, 2030)).sum())
    value_series = pd.to_numeric(df["value"], errors="coerce")
    invalid_value_count = int(df["value"].notna().sum() - value_series.notna().sum())
    metadata_null_count = int(
        df[["run_id", "run_date", "loaded_at"]].isna().any(axis=1).sum()
    )

    duplicate_key_count = int(
        df.duplicated(subset=["country_code", "year", "indicator", "source"]).sum()
    )

    if invalid_sources:
        raise ValueError(f"Invalid source values found: {invalid_sources}")
    if invalid_country_code_count:
        raise ValueError(f"Invalid country_code values found: {invalid_country_code_count}")
    if invalid_year_count:
        raise ValueError(f"Invalid year values found: {invalid_year_count}")
    if invalid_value_count:
        raise ValueError(f"Invalid value entries found: {invalid_value_count}")
    if metadata_null_count:
        raise ValueError(f"Missing required metadata values found: {metadata_null_count}")
    if duplicate_key_count:
        raise ValueError(f"duplicate_key_count={duplicate_key_count}")

    return {
        "observed_sources": observed_sources,
        "observed_canonical_sources": canonical_sources,
        "invalid_sources": invalid_sources,
        "invalid_country_code_count": invalid_country_code_count,
        "invalid_year_count": invalid_year_count,
        "invalid_value_count": invalid_value_count,
        "metadata_null_count": metadata_null_count,
        "duplicate_key_count": duplicate_key_count,
        "year_min": int(pd.to_numeric(df["year"], errors="coerce").min()),
        "year_max": int(pd.to_numeric(df["year"], errors="coerce").max()),
        "null_value_rate": float(df["value"].isna().sum() / len(df)),
    }


def _manifest_summary(
    *,
    manifest: dict[str, Any],
    local_silver_path: Path,
    local_manifest_path: Path,
    source_format: str,
) -> dict[str, Any]:
    validation = manifest.get("validation_summary") or {}
    manifest_output_path = _manifest_output_path(manifest, local_manifest_path)
    manifest_run_id = str(manifest.get("run_id") or "")
    manifest_run_date = str(manifest.get("run_date") or "")

    return {
        "manifest_run_id": manifest_run_id,
        "manifest_run_date": manifest_run_date,
        "manifest_output_path": str(manifest_output_path) if manifest_output_path else None,
        "manifest_path_matches_input": manifest_output_path is not None
        and manifest_output_path.resolve() == local_silver_path.resolve(),
        "manifest_output_format": str(manifest.get("output_format") or "").strip().lower(),
        "manifest_validation_summary": validation,
        "source_format_matches_manifest": str(manifest.get("output_format") or "").strip().lower()
        == source_format,
    }


def build_silver_load_plan(
    *,
    silver_output_dir: str | None = None,
    silver_manifest: str | None = None,
    project_id: str = TARGET_PROJECT_ID,
    dataset: str = TARGET_DATASET,
    table: str = TARGET_TABLE,
    location: str = TARGET_LOCATION,
    write_disposition: str = DEFAULT_WRITE_DISPOSITION,
    output_dir: str | Path | None = None,
    run_id: str | None = None,
    run_date: str | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    base_repo = (repo_root or _repo_root()).resolve()
    artifacts = resolve_silver_artifacts(
        silver_output_dir=silver_output_dir,
        silver_manifest=silver_manifest,
        repo_root=base_repo,
    )
    contract_payload = _load_contract(base_repo)
    contract_columns = _list_contract_columns(contract_payload)
    local_frame = _load_local_frame(artifacts.local_silver_path, artifacts.source_format)

    if local_frame.empty:
        raise ValueError(f"Local Silver output is empty: {artifacts.local_silver_path}")

    actual_columns = list(local_frame.columns)
    schema_summary = _validate_columns(
        actual_columns=actual_columns,
        contract_columns=contract_columns,
    )
    value_summary = _validate_values(local_frame)

    manifest_run_id = str(artifacts.manifest.get("run_id") or "")
    manifest_run_date = str(artifacts.manifest.get("run_date") or "")
    if run_id and run_id != manifest_run_id:
        raise ValueError(
            f"run_id mismatch: arg={run_id!r} manifest={manifest_run_id!r}"
        )
    if run_date and run_date != manifest_run_date:
        raise ValueError(
            f"run_date mismatch: arg={run_date!r} manifest={manifest_run_date!r}"
        )

    expected_table_id = build_table_id(project_id, dataset, table)
    if expected_table_id != TARGET_TABLE_ID:
        raise ValueError(
            "Target table identity must be exact: "
            f"expected={TARGET_TABLE_ID!r} actual={expected_table_id!r}"
        )

    manifest_source_counts = _source_counts_from_manifest(artifacts.manifest)
    computed_source_counts = _source_counts_from_frame(local_frame)
    if manifest_source_counts is not None and manifest_source_counts != computed_source_counts:
        raise ValueError(
            "Manifest source_counts do not match local Silver output: "
            f"manifest={manifest_source_counts!r} computed={computed_source_counts!r}"
        )

    manifest_validation = artifacts.manifest.get("validation_summary") or {}
    manifest_row_count = manifest_validation.get("row_count")
    manifest_country_count = manifest_validation.get("country_count")
    manifest_indicator_count = manifest_validation.get("indicator_count")
    manifest_duplicate_count = manifest_validation.get("duplicate_key_count")

    computed_row_count = int(len(local_frame))
    computed_country_count = int(local_frame["country_code"].nunique(dropna=True))
    computed_indicator_count = int(local_frame["indicator"].nunique(dropna=True))
    computed_duplicate_count = int(value_summary["duplicate_key_count"])

    if manifest_row_count is not None and int(manifest_row_count) != computed_row_count:
        raise ValueError(
            f"Manifest row_count mismatch: manifest={manifest_row_count!r} computed={computed_row_count!r}"
        )
    if manifest_country_count is not None and int(manifest_country_count) != computed_country_count:
        raise ValueError(
            "Manifest country_count mismatch: "
            f"manifest={manifest_country_count!r} computed={computed_country_count!r}"
        )
    if manifest_indicator_count is not None and int(manifest_indicator_count) != computed_indicator_count:
        raise ValueError(
            "Manifest indicator_count mismatch: "
            f"manifest={manifest_indicator_count!r} computed={computed_indicator_count!r}"
        )
    if manifest_duplicate_count is not None and int(manifest_duplicate_count) != computed_duplicate_count:
        raise ValueError(
            "Manifest duplicate_key_count mismatch: "
            f"manifest={manifest_duplicate_count!r} computed={computed_duplicate_count!r}"
        )

    data_files = _data_files(artifacts.local_silver_path)
    estimated_input_files = len(data_files)
    estimated_input_bytes = int(sum(item.stat().st_size for item in data_files))

    manifest_summary = _manifest_summary(
        manifest=artifacts.manifest,
        local_silver_path=artifacts.local_silver_path,
        local_manifest_path=artifacts.local_manifest_path,
        source_format=artifacts.source_format,
    )

    source_counts = manifest_source_counts or computed_source_counts
    exact_next_command = _expected_next_load_command(
        silver_output_path=artifacts.local_silver_path,
        silver_manifest_path=artifacts.local_manifest_path,
        project_id=project_id,
        dataset=dataset,
        table=table,
        location=location,
        write_disposition=write_disposition,
    )

    plan: dict[str, Any] = {
        "project_id": project_id,
        "dataset": dataset,
        "table": table,
        "table_id": expected_table_id,
        "location": location,
        "source_format": artifacts.source_format,
        "local_silver_path": str(artifacts.local_silver_path),
        "local_manifest_path": str(artifacts.local_manifest_path),
        "required_columns": list(REQUIRED_COLUMNS),
        "contract_columns": contract_columns,
        "schema_validation_summary": {
            **schema_summary,
            **value_summary,
            **manifest_summary,
            "source_counts_match_manifest": manifest_source_counts == computed_source_counts
            if manifest_source_counts is not None
            else None,
        },
        "row_count": int(manifest_row_count) if manifest_row_count is not None else computed_row_count,
        "country_count": int(manifest_country_count) if manifest_country_count is not None else computed_country_count,
        "indicator_count": int(manifest_indicator_count) if manifest_indicator_count is not None else computed_indicator_count,
        "source_counts": source_counts,
        "duplicate_key_count": int(manifest_duplicate_count)
        if manifest_duplicate_count is not None
        else computed_duplicate_count,
        "write_disposition": write_disposition,
        "create_disposition": DEFAULT_CREATE_DISPOSITION,
        "partition": contract_payload.get("silver", {})
        .get(TARGET_TABLE, {})
        .get("partition"),
        "cluster": contract_payload.get("silver", {})
        .get(TARGET_TABLE, {})
        .get("cluster"),
        "estimated_input_files": estimated_input_files,
        "estimated_input_bytes": estimated_input_bytes,
        "dry_run": True,
        "bigquery_write_approved": False,
        "job_started": False,
        "run_id": manifest_run_id or run_id,
        "run_date": manifest_run_date or run_date,
        "next_load_command": exact_next_command,
        "required_approval_env": "BIGQUERY_WRITE_APPROVED=true",
        "write_enabled": False,
        "artifacts_detection_mode": artifacts.detection_mode,
        "artifacts_checked_paths": list(artifacts.checked_paths),
    }
    return plan


def write_load_plan_artifacts(plan: dict[str, Any], output_dir: str | Path) -> dict[str, Path]:
    target_dir = Path(output_dir).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    plan_path = target_dir / "load_plan.json"
    summary_path = target_dir / "load_plan_summary.txt"

    plan_path.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary_lines = [
        "BigQuery Silver BigQuery Silver load dry-run",
        f"Target table: {plan['table_id']}",
        f"Local Silver: {plan['local_silver_path']}",
        f"Manifest: {plan['local_manifest_path']}",
        f"Source format: {plan['source_format']}",
        f"Row count: {plan['row_count']}",
        f"Country count: {plan['country_count']}",
        f"Indicator count: {plan['indicator_count']}",
        f"Source counts: {json.dumps(plan['source_counts'], sort_keys=True, ensure_ascii=False)}",
        f"Duplicate key count: {plan.get('duplicate_key_count')}",
        f"Estimated input files: {plan['estimated_input_files']}",
        f"Estimated input bytes: {plan['estimated_input_bytes']}",
        f"dry_run={plan['dry_run']}",
        f"bigquery_write_approved={plan['bigquery_write_approved']}",
        f"job_started={plan['job_started']}",
        "BigQuery write is disabled unless BIGQUERY_WRITE_APPROVED=true.",
        f"Next command: {plan['next_load_command']}",
    ]
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    return {"load_plan": plan_path, "summary": summary_path}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan a dry-run BigQuery load for the local silver_indicators output."
    )
    parser.add_argument("--silver-output-dir", default=None)
    parser.add_argument("--silver-manifest", default=None)
    parser.add_argument("--project-id", default=TARGET_PROJECT_ID)
    parser.add_argument("--dataset", default=TARGET_DATASET)
    parser.add_argument("--table", default=TARGET_TABLE)
    parser.add_argument("--location", default=TARGET_LOCATION)
    parser.add_argument("--write-disposition", default=DEFAULT_WRITE_DISPOSITION)
    parser.add_argument("--output-dir", default="../../tmp/bigquery_silver_load_plan")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--run-date", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plan = build_silver_load_plan(
        silver_output_dir=args.silver_output_dir,
        silver_manifest=args.silver_manifest,
        project_id=args.project_id,
        dataset=args.dataset,
        table=args.table,
        location=args.location,
        write_disposition=args.write_disposition,
        output_dir=args.output_dir,
        run_id=args.run_id,
        run_date=args.run_date,
    )
    artifacts = write_load_plan_artifacts(plan, args.output_dir)
    print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"load_plan_path={artifacts['load_plan']}")
    print(f"summary_path={artifacts['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
