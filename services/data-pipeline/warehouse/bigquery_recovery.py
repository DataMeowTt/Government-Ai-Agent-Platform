from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from warehouse.bigquery_warehouse_validation import parse_table_id


DEFAULT_RETENTION_DAYS = 45
DEFAULT_APPROVAL_ENV = "BIGQUERY_WAREHOUSE_WRITE_APPROVED"

PRODUCTION_TABLE_ORDER = [
    "western-pivot-452008-a6.gov_ai_silver.silver_indicators",
    "western-pivot-452008-a6.gov_ai_gold.gold_growth_dynamics",
    "western-pivot-452008-a6.gov_ai_gold.gold_fiscal_monetary",
    "western-pivot-452008-a6.gov_ai_gold.gold_crisis_risk",
    "western-pivot-452008-a6.gov_ai_gold.gold_social_welfare",
    "western-pivot-452008-a6.gov_ai_gold.gold_structural_composition",
    "western-pivot-452008-a6.gov_ai_analytics.analytics_gold_growth_dynamics",
    "western-pivot-452008-a6.gov_ai_analytics.analytics_gold_fiscal_monetary",
    "western-pivot-452008-a6.gov_ai_analytics.analytics_gold_crisis_risk",
    "western-pivot-452008-a6.gov_ai_analytics.analytics_gold_social_welfare",
    "western-pivot-452008-a6.gov_ai_analytics.analytics_gold_structural_composition",
    "western-pivot-452008-a6.gov_ai_analytics.analytics_clusters",
]


class RecoveryCollisionError(RuntimeError):
    pass


def _safe_token(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", str(value or "").strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "run"


def retention_days_from_env(env_getter: Callable[[str], str | None] = os.getenv) -> int:
    raw = str(env_getter("RECOVERY_TABLE_RETENTION_DAYS") or "").strip()
    if not raw:
        return DEFAULT_RETENTION_DAYS
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"RECOVERY_TABLE_RETENTION_DAYS must be an integer, got: {raw!r}") from exc
    if value < 1 or value > 365:
        raise ValueError(f"RECOVERY_TABLE_RETENTION_DAYS must be between 1 and 365, got: {value}")
    return value


def recovery_table_id_for(production_table_id: str, run_id: str) -> str:
    project_id, dataset, table = parse_table_id(production_table_id)
    token = _safe_token(run_id)
    return f"{project_id}.{dataset}.{table}_recovery_run_{token}"


def build_recovery_plan(*, production_table_ids: list[str], run_id: str) -> list[dict[str, str]]:
    plan: list[dict[str, str]] = []
    for production_table_id in production_table_ids:
        plan.append(
            {
                "production_table_id": production_table_id,
                "recovery_table_id": recovery_table_id_for(production_table_id, run_id),
            }
        )
    return plan


def _client(project_id: str) -> Any:
    from google.cloud import bigquery

    return bigquery.Client(project=project_id)


def _table_exists(client: Any, table_id: str) -> bool:
    try:
        client.get_table(table_id)
        return True
    except Exception:
        return False


def _require_approval(approval_env: str, env_getter: Callable[[str], str | None]) -> None:
    if str(env_getter(approval_env) or "").strip().lower() != "true":
        raise RuntimeError(f"{approval_env} must be true before recovery backup/restore operations.")


@dataclass(frozen=True)
class RecoveryBackup:
    production_table_id: str
    recovery_table_id: str
    copy_job_id: str
    source_row_count: int
    recovery_row_count: int
    expiration_time_utc: str


def prepare_recovery_backups(
    *,
    project_id: str,
    location: str,
    production_table_ids: list[str],
    run_id: str,
    retention_days: int,
    approval_env: str = DEFAULT_APPROVAL_ENV,
    env_getter: Callable[[str], str | None] = os.getenv,
    client_factory: Callable[[str], Any] = _client,
) -> dict[str, Any]:
    _require_approval(approval_env, env_getter)
    client = client_factory(project_id)
    expire_at = datetime.now(timezone.utc) + timedelta(days=int(retention_days))
    plan = build_recovery_plan(production_table_ids=production_table_ids, run_id=run_id)

    preexisting = [item for item in plan if _table_exists(client, item["recovery_table_id"])]
    if preexisting:
        raise RecoveryCollisionError(
            f"Recovery table collision detected before production mutation: {[item['recovery_table_id'] for item in preexisting]}"
        )

    from google.cloud import bigquery

    backups: list[RecoveryBackup] = []
    for item in plan:
        source_table = item["production_table_id"]
        recovery_table = item["recovery_table_id"]
        config = bigquery.CopyJobConfig(
            create_disposition=bigquery.CreateDisposition.CREATE_IF_NEEDED,
            write_disposition=bigquery.WriteDisposition.WRITE_EMPTY,
        )
        job = client.copy_table(
            source_table,
            recovery_table,
            job_config=config,
            location=location,
        )
        job.result()
        recovery_meta = client.get_table(recovery_table)
        setattr(recovery_meta, "expires", expire_at)
        client.update_table(recovery_meta, ["expires"])
        source_rows = int(getattr(client.get_table(source_table), "num_rows", 0))
        recovery_rows = int(getattr(client.get_table(recovery_table), "num_rows", 0))
        if source_rows != recovery_rows:
            raise RuntimeError(
                f"Recovery row_count mismatch for {recovery_table}: source={source_rows} recovery={recovery_rows}"
            )
        backups.append(
            RecoveryBackup(
                production_table_id=source_table,
                recovery_table_id=recovery_table,
                copy_job_id=str(job.job_id),
                source_row_count=source_rows,
                recovery_row_count=recovery_rows,
                expiration_time_utc=expire_at.isoformat(),
            )
        )

    return {
        "status": "RECOVERY_READY",
        "retention_days": int(retention_days),
        "run_id": run_id,
        "approval_env": approval_env,
        "backups": [item.__dict__ for item in backups],
    }


def restore_production_tables(
    *,
    project_id: str,
    location: str,
    touched_production_tables: list[str],
    backup_payload: dict[str, Any],
    approval_env: str = DEFAULT_APPROVAL_ENV,
    env_getter: Callable[[str], str | None] = os.getenv,
    client_factory: Callable[[str], Any] = _client,
) -> dict[str, Any]:
    _require_approval(approval_env, env_getter)
    client = client_factory(project_id)
    from google.cloud import bigquery

    mapping = {
        str(item["production_table_id"]): str(item["recovery_table_id"])
        for item in list(backup_payload.get("backups") or [])
    }
    restored: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for production_table_id in touched_production_tables:
        recovery_table_id = mapping.get(production_table_id)
        if not recovery_table_id:
            failed.append(
                {
                    "production_table_id": production_table_id,
                    "recovery_table_id": None,
                    "error_message": "missing_recovery_mapping",
                }
            )
            continue
        try:
            copy_job = client.copy_table(
                recovery_table_id,
                production_table_id,
                job_config=bigquery.CopyJobConfig(
                    write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
                ),
                location=location,
            )
            copy_job.result()
            recovery_rows = int(getattr(client.get_table(recovery_table_id), "num_rows", 0))
            production_rows = int(getattr(client.get_table(production_table_id), "num_rows", 0))
            if recovery_rows != production_rows:
                raise RuntimeError(
                    f"post-restore row_count mismatch: recovery={recovery_rows} production={production_rows}"
                )
            restored.append(
                {
                    "production_table_id": production_table_id,
                    "recovery_table_id": recovery_table_id,
                    "copy_job_id": str(copy_job.job_id),
                    "row_count": production_rows,
                }
            )
        except Exception as exc:
            failed.append(
                {
                    "production_table_id": production_table_id,
                    "recovery_table_id": recovery_table_id,
                    "error_message": str(exc),
                }
            )

    return {
        "status": "RESTORE_SUCCEEDED" if not failed else "RESTORE_FAILED",
        "restored": restored,
        "failed": failed,
    }
