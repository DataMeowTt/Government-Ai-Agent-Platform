from __future__ import annotations


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
    return plan

