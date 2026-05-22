from __future__ import annotations

from src.adapters.bigquery import (
    DEFAULT_ANALYTICS_DATASET,
    DEFAULT_BIGQUERY_LOCATION,
    BigQueryAnalyticsAdapter,
)
from src.adapters.postgres import PostgresAnalyticsAdapter


def get_analytics_adapter(
    target: str,
    *,
    project_id: str | None = None,
    dataset: str = DEFAULT_ANALYTICS_DATASET,
    location: str = DEFAULT_BIGQUERY_LOCATION,
):
    clean_target = str(target or "").strip().lower()

    if clean_target == "postgres":
        return PostgresAnalyticsAdapter()

    if clean_target == "bigquery":
        return BigQueryAnalyticsAdapter(
            project_id=project_id or "",
            dataset=dataset,
            location=location,
        )

    raise ValueError(f"Unsupported analytics target: {target}")
