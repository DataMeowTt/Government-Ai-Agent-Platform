from __future__ import annotations

from src.adapters.base import AnalyticsWritePlan


POSTGRES_ANALYTICS_REQUIRED_COLUMNS = (
    "country_code",
    "year",
    "run_id",
    "run_date",
    "loaded_at",
)

POSTGRES_CLUSTER_REQUIRED_COLUMNS = (
    "year",
    "country_code",
    "cluster_id",
    "latest_valid_year",
    "method",
    "run_id",
    "run_date",
    "loaded_at",
)


class PostgresAnalyticsAdapter:
    target = "postgres"
    supports_dry_run = True

    def build_indicator_plan(
        self,
        source_table: str,
        indicators: list[str],
        *,
        dry_run: bool,
    ) -> AnalyticsWritePlan:
        table = f"analytics_{source_table}"
        return AnalyticsWritePlan(
            target=self.target,
            table=table,
            table_id=table,
            source_table=source_table,
            indicators=tuple(indicators),
            required_columns=POSTGRES_ANALYTICS_REQUIRED_COLUMNS,
            dry_run=dry_run,
        )

    def build_cluster_plan(
        self,
        cluster_years: list[int],
        *,
        dry_run: bool,
        latest_valid_year: int | None = None,
    ) -> AnalyticsWritePlan:
        return AnalyticsWritePlan(
            target=self.target,
            table="analytics_clusters",
            table_id="analytics_clusters",
            required_columns=POSTGRES_CLUSTER_REQUIRED_COLUMNS,
            cluster_years=tuple(cluster_years),
            latest_valid_year=latest_valid_year,
            dry_run=dry_run,
        )

    def ensure_can_execute(self, *, dry_run: bool) -> None:
        return None
