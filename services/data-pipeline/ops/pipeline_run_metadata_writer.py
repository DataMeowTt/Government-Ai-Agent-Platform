from __future__ import annotations

from typing import Any, Callable

from ops.ops_writer import OPS_DATASET, build_ops_writer_plan


DEFAULT_APPROVAL_ENV = "BIGQUERY_OPS_WRITE_APPROVED"
PIPELINE_RUN_METADATA_TABLE = "pipeline_run_metadata"


def require_ops_write_approval(env_getter: Callable[[str], str | None], env_name: str = DEFAULT_APPROVAL_ENV) -> str:
    value = env_getter(env_name)
    if value != "true":
        raise RuntimeError(f"{env_name} must be exactly true before ops metadata write; observed={value!r}")
    return value


def validate_metadata_row(row: dict[str, Any], *, project_id: str) -> dict[str, Any]:
    plan = build_ops_writer_plan({"pipeline_run_metadata": [dict(row)]}, project_id=project_id)
    entry = next(item for item in plan if item["table"] == PIPELINE_RUN_METADATA_TABLE)
    validation = dict(entry["validation"])
    if validation.get("status") != "passed":
        raise ValueError(f"pipeline_run_metadata validation failed: {validation.get('row_errors')}")
    return validation


def _default_append_rows(*, table_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    from google.cloud import bigquery

    project_id = table_id.split(".", 1)[0]
    client = bigquery.Client(project=project_id)
    table = client.get_table(table_id)
    errors = client.insert_rows(table=table, rows=rows)
    if errors:
        raise RuntimeError(f"BigQuery insert_rows_json failed for {table_id}: {errors}")
    return {"table_id": table_id, "inserted_row_count": len(rows)}


def append_pipeline_run_metadata_row(
    *,
    row: dict[str, Any],
    project_id: str,
    env_getter: Callable[[str], str | None],
    row_appender: Callable[..., dict[str, Any]] | None = None,
    approval_env: str = DEFAULT_APPROVAL_ENV,
) -> dict[str, Any]:
    approval_value = require_ops_write_approval(env_getter, approval_env)
    validation = validate_metadata_row(row, project_id=project_id)
    table_id = f"{project_id}.{OPS_DATASET}.{PIPELINE_RUN_METADATA_TABLE}"
    appender = row_appender or _default_append_rows
    append_result = appender(table_id=table_id, rows=[dict(row)])
    return {
        "table_id": table_id,
        "approval_env": approval_env,
        "approval_value": approval_value,
        "validation": validation,
        "append_result": append_result,
    }
