from __future__ import annotations

import re

from src.adapters.base import AnalyticsWritePlan


DEFAULT_ANALYTICS_DATASET = "gov_ai_analytics"
DEFAULT_BIGQUERY_LOCATION = "asia-southeast1"

ANALYTICS_REQUIRED_COLUMNS = (
    "country_code",
    "country",
    "year",
    "run_id",
    "run_date",
    "loaded_at",
)

ANALYTICS_CLUSTER_REQUIRED_COLUMNS = (
    "country_code",
    "country",
    "year",
    "cluster_id",
    "latest_valid_year",
    "run_id",
    "run_date",
    "loaded_at",
)

_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


def validate_dataset_name(dataset: str) -> str:
    cleaned = str(dataset or "").strip()
    if not cleaned:
        raise ValueError("dataset is required.")
    if not _SAFE_NAME_RE.match(cleaned):
        raise ValueError(
            f"Unsafe BigQuery dataset name: {cleaned!r}. "
            "Use only letters, numbers, and underscores."
        )
    return cleaned


def validate_table_name(table: str) -> str:
    cleaned = str(table or "").strip()
    if not cleaned:
        raise ValueError("table is required.")
    if not _SAFE_NAME_RE.match(cleaned):
        raise ValueError(
            f"Unsafe BigQuery table name: {cleaned!r}. "
            "Use only letters, numbers, and underscores."
        )
    return cleaned


def build_table_id(project_id: str, dataset: str, table: str) -> str:
    clean_project_id = str(project_id or "").strip()
    if not clean_project_id:
        raise ValueError("project_id is required for BigQuery target.")
    return f"{clean_project_id}.{validate_dataset_name(dataset)}.{validate_table_name(table)}"


class BigQueryAnalyticsAdapter:
    target = "bigquery"
    supports_dry_run = True

    def __init__(
        self,
        *,
        project_id: str,
        dataset: str = DEFAULT_ANALYTICS_DATASET,
        location: str = DEFAULT_BIGQUERY_LOCATION,
    ) -> None:
        self.project_id = str(project_id or "").strip()
        if not self.project_id:
            raise ValueError("project_id is required for BigQuery target.")
        self.dataset = validate_dataset_name(dataset)
        self.location = str(location or DEFAULT_BIGQUERY_LOCATION).strip()

    def build_indicator_plan(
        self,
        source_table: str,
        indicators: list[str],
        *,
        dry_run: bool,
    ) -> AnalyticsWritePlan:
        table = validate_table_name(f"analytics_{source_table}")
        return AnalyticsWritePlan(
            target=self.target,
            project_id=self.project_id,
            dataset=self.dataset,
            location=self.location,
            table=table,
            table_id=build_table_id(self.project_id, self.dataset, table),
            source_table=source_table,
            indicators=tuple(indicators),
            required_columns=ANALYTICS_REQUIRED_COLUMNS,
            dry_run=dry_run,
            job_started=False,
            note="dry_run=true; no BigQuery job was started.",
        )

    def build_cluster_plan(
        self,
        cluster_years: list[int],
        *,
        dry_run: bool,
        latest_valid_year: int | None = None,
    ) -> AnalyticsWritePlan:
        table = "analytics_clusters"
        return AnalyticsWritePlan(
            target=self.target,
            project_id=self.project_id,
            dataset=self.dataset,
            location=self.location,
            table=table,
            table_id=build_table_id(self.project_id, self.dataset, table),
            required_columns=ANALYTICS_CLUSTER_REQUIRED_COLUMNS,
            cluster_years=tuple(cluster_years),
            latest_valid_year=latest_valid_year,
            dry_run=dry_run,
            job_started=False,
            note="dry_run=true; no BigQuery job was started.",
        )

    def ensure_can_execute(self, *, dry_run: bool) -> None:
        if dry_run:
            return None

        raise RuntimeError(
            "Real BigQuery analytics execution is not enabled for this dry-run adapter. "
            "Use --dry-run until credentials, project, location, and side effects are explicitly confirmed."
        )
