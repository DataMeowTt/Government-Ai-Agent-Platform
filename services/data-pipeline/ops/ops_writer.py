from __future__ import annotations

import json


OPS_DATASET = "gov_ai_ops"
WRITE_DISPOSITION = "WRITE_APPEND"

PIPELINE_RUNS_REQUIRED = (
    "run_id",
    "run_date",
    "status",
    "source_changed",
    "raw_hashes",
    "silver_rows",
    "gold_rows",
    "analytics_rows",
    "started_at",
    "finished_at",
    "error_message",
)
SOURCE_SNAPSHOTS_REQUIRED = (
    "run_id",
    "run_date",
    "source_name",
    "status",
    "file_count",
    "total_bytes",
    "combined_hash",
    "manifest_path",
    "recorded_at",
)
JOB_LOGS_REQUIRED = (
    "run_id",
    "run_date",
    "job_name",
    "status",
    "started_at",
    "finished_at",
    "error_message",
)
REQUIRED_FIELDS = {
    "pipeline_runs": PIPELINE_RUNS_REQUIRED,
    "source_snapshots": SOURCE_SNAPSHOTS_REQUIRED,
    "job_logs": JOB_LOGS_REQUIRED,
}

PIPELINE_RUN_METADATA_REQUIRED = (
    "run_id",
    "run_date",
    "execution_mode",
    "status",
    "started_at",
    "enabled_sources",
    "changed_sources",
    "bronze_write_planned",
    "bronze_write_performed",
    "warehouse_publish_planned",
    "warehouse_publish_performed",
    "last_successful_updated",
    "force_requested",
    "force_applied",
    "planned_actions",
    "cloud_write",
    "publish_performed",
)

NON_PUBLISHING_READINESS_STATUSES = {
    "PLANNED_CHANGED",
    "PLANNED_UNCHANGED",
    "DRY_RUN_CHANGED",
    "SKIPPED_UNCHANGED",
    "BLOCKED_APPROVAL_REQUIRED",
}

FAILURE_STATUSES = {
    "FAILED",
    "VALIDATION_FAILED",
    "PUBLISH_FAILED",
    "ACQUISITION_FAILED",
    "BASELINE_INVALID",
}


def build_table_id(project_id: str | None, dataset: str, table: str) -> str | None:
    clean_project = str(project_id or "").strip()
    if not clean_project:
        return None
    return f"{clean_project}.{dataset}.{table}"


def validate_rows(table: str, rows: list[dict]) -> dict:
    required = REQUIRED_FIELDS[table]
    row_errors: list[dict] = []
    for index, row in enumerate(rows):
        missing = [field for field in required if field not in row]
        if missing:
            row_errors.append({"row_index": index, "missing_fields": missing})

    return {
        "status": "passed" if not row_errors else "failed",
        "required_fields": list(required),
        "row_errors": row_errors,
    }


def _is_blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def _is_valid_latest_data_year(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value > 0
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return False
        try:
            return int(text) > 0
        except ValueError:
            return False
    return False


def _is_valid_sources_json(value: object) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text:
        return False
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return False
    return isinstance(parsed, (dict, list))


def _is_gcs_uri(value: object) -> bool:
    return isinstance(value, str) and value.startswith("gs://") and len(value.strip()) > 5


def _metadata_semantic_errors(row: dict) -> list[str]:
    status = str(row.get("status") or "").strip().upper()
    errors: list[str] = []
    warehouse_publish_performed = row.get("warehouse_publish_performed")
    publish_performed = row.get("publish_performed")
    last_successful_updated = row.get("last_successful_updated")
    published_at = row.get("published_at")

    if status == "SUCCESS":
        if warehouse_publish_performed is not True:
            errors.append("SUCCESS requires warehouse_publish_performed=True")
        if publish_performed is not True:
            errors.append("SUCCESS requires publish_performed=True")
        if last_successful_updated is not True:
            errors.append("SUCCESS requires last_successful_updated=True")
        if _is_blank(published_at):
            errors.append("SUCCESS requires published_at to be non-empty")
        if not _is_valid_latest_data_year(row.get("latest_data_year")):
            errors.append("SUCCESS requires latest_data_year to be a valid integer")
        if not _is_valid_sources_json(row.get("sources_json")):
            errors.append("SUCCESS requires sources_json to be valid JSON metadata")
        candidate_manifest_path = row.get("candidate_source_manifest_path")
        if _is_blank(candidate_manifest_path):
            errors.append("SUCCESS requires candidate_source_manifest_path to be non-empty")
        elif not _is_gcs_uri(candidate_manifest_path):
            errors.append("SUCCESS requires candidate_source_manifest_path to be a durable gs:// URI")
        return errors

    if status in NON_PUBLISHING_READINESS_STATUSES or status in FAILURE_STATUSES or status.endswith("FAILED"):
        if warehouse_publish_performed is not False:
            errors.append(f"{status} requires warehouse_publish_performed=False")
        if publish_performed is not False:
            errors.append(f"{status} requires publish_performed=False")
        if last_successful_updated is not False:
            errors.append(f"{status} requires last_successful_updated=False")
        if not _is_blank(published_at):
            errors.append(f"{status} requires published_at to be empty")
    return errors


def _validate_pipeline_run_metadata_rows(rows: list[dict]) -> dict:
    row_errors: list[dict] = []
    required = list(PIPELINE_RUN_METADATA_REQUIRED)

    for index, row in enumerate(rows):
        missing_fields = [field for field in required if field not in row]
        semantic_errors = _metadata_semantic_errors(row)
        if missing_fields or semantic_errors:
            row_errors.append(
                {
                    "row_index": index,
                    "missing_fields": missing_fields,
                    "semantic_errors": semantic_errors,
                }
            )

    return {
        "status": "passed" if not row_errors else "failed",
        "required_fields": required,
        "row_errors": row_errors,
    }


def build_ops_writer_plan(ops_records: dict, *, project_id: str | None = None) -> list[dict]:
    plan: list[dict] = []
    for table in ("pipeline_runs", "source_snapshots", "job_logs"):
        rows = list(ops_records.get(table, []))
        plan.append(
            {
                "dataset": OPS_DATASET,
                "table": table,
                "table_id": build_table_id(project_id, OPS_DATASET, table),
                "row_count": len(rows),
                "rows_preview": rows[:3],
                "dry_run": True,
                "write_disposition": WRITE_DISPOSITION,
                "validation": validate_rows(table, rows),
            }
        )
    metadata_rows = list(ops_records.get("pipeline_run_metadata", []))
    if metadata_rows:
        plan.append(
            {
                "dataset": OPS_DATASET,
                "table": "pipeline_run_metadata",
                "table_id": build_table_id(project_id, OPS_DATASET, "pipeline_run_metadata"),
                "row_count": len(metadata_rows),
                "rows_preview": metadata_rows[:1],
                "dry_run": True,
                "write_disposition": WRITE_DISPOSITION,
                "validation": _validate_pipeline_run_metadata_rows(metadata_rows),
            }
        )
    return plan
