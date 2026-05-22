from __future__ import annotations

import re
from typing import Any

from app.core.config import settings
from app.db.bigquery import run_bigquery_query
from app.tools.common import ToolError


_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SELECT_STAR_PATTERN = re.compile(r"\bselect\s+\*", re.IGNORECASE)


def _normalized_setting(value: str, fallback: str) -> str:
    stripped = (value or "").strip()
    return stripped or fallback


def _build_fqdn(project: str, dataset: str, table: str) -> str:
    return f"{project}.{dataset}.{table}"


_PROJECT_ID = _normalized_setting(settings.bigquery_project_id, "western-pivot-452008-a6")
_GOLD_DATASET = _normalized_setting(settings.bigquery_gold_dataset, "gov_ai_gold")
_ANALYTICS_DATASET = _normalized_setting(
    settings.bigquery_analytics_dataset,
    "gov_ai_analytics",
)

_SHORT_TO_FQDN = {
    "gold_growth_dynamics": _build_fqdn(
        _PROJECT_ID,
        _GOLD_DATASET,
        "gold_growth_dynamics",
    ),
    "gold_fiscal_monetary": _build_fqdn(
        _PROJECT_ID,
        _GOLD_DATASET,
        "gold_fiscal_monetary",
    ),
    "gold_crisis_risk": _build_fqdn(
        _PROJECT_ID,
        _GOLD_DATASET,
        "gold_crisis_risk",
    ),
    "gold_social_welfare": _build_fqdn(
        _PROJECT_ID,
        _GOLD_DATASET,
        "gold_social_welfare",
    ),
    "gold_structural_composition": _build_fqdn(
        _PROJECT_ID,
        _GOLD_DATASET,
        "gold_structural_composition",
    ),
    "analytics_gold_growth_dynamics": _build_fqdn(
        _PROJECT_ID,
        _ANALYTICS_DATASET,
        "analytics_gold_growth_dynamics",
    ),
    "analytics_gold_fiscal_monetary": _build_fqdn(
        _PROJECT_ID,
        _ANALYTICS_DATASET,
        "analytics_gold_fiscal_monetary",
    ),
    "analytics_gold_crisis_risk": _build_fqdn(
        _PROJECT_ID,
        _ANALYTICS_DATASET,
        "analytics_gold_crisis_risk",
    ),
    "analytics_gold_social_welfare": _build_fqdn(
        _PROJECT_ID,
        _ANALYTICS_DATASET,
        "analytics_gold_social_welfare",
    ),
    "analytics_gold_structural_composition": _build_fqdn(
        _PROJECT_ID,
        _ANALYTICS_DATASET,
        "analytics_gold_structural_composition",
    ),
    "analytics_clusters": _build_fqdn(
        _PROJECT_ID,
        _ANALYTICS_DATASET,
        "analytics_clusters",
    ),
}

_TABLE_WHITELIST: frozenset[str] = frozenset(_SHORT_TO_FQDN.values())


def list_whitelisted_tables() -> list[str]:
    return sorted(_TABLE_WHITELIST)


def resolve_whitelisted_table(table_name: str | None) -> str:
    if not table_name:
        raise ToolError("Missing table name")

    fqdn = _SHORT_TO_FQDN.get(table_name, table_name)
    if fqdn not in _TABLE_WHITELIST:
        raise ToolError(f"Table is not whitelisted: {table_name}")
    return fqdn


def safe_identifier(identifier: str) -> str:
    if not _IDENTIFIER_PATTERN.match(identifier):
        raise ToolError(f"Unsafe identifier: {identifier}")
    return f"`{identifier}`"


def sanitize_query_params(params: dict[str, Any] | None) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in (params or {}).items():
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            filtered = [item for item in value if item is not None]
            if not filtered:
                continue
            cleaned[key] = filtered
            continue
        cleaned[key] = value
    return cleaned


def execute_bigquery_select(
    *,
    sql: str,
    referenced_tables: list[str],
    params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if _SELECT_STAR_PATTERN.search(sql):
        raise ToolError("SELECT * is not allowed")

    resolved_tables = [resolve_whitelisted_table(table) for table in referenced_tables]
    for table in resolved_tables:
        if table not in sql:
            raise ToolError(f"SQL does not reference required table: {table}")

    cleaned_params = sanitize_query_params(params)
    return run_bigquery_query(sql, cleaned_params)
