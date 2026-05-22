from app.catalog.canonical_indicator_catalog import (
    ANALYTICS_INDICATORS_BY_GOLD_TABLE,
    ANALYTICS_SUFFIXES,
    CLUSTER_INDICATORS,
    get_analytics_columns,
    get_analytics_table_for_indicator,
    get_indicator_analytics_metadata,
    indicator_has_analytics,
    indicator_supports_anomaly,
    indicator_supports_trend,
    indicator_used_for_cluster,
)


ANALYTICS_TABLES_INDICATORS: dict[str, list[str]] = {
    gold_table: list(indicators)
    for gold_table, indicators in ANALYTICS_INDICATORS_BY_GOLD_TABLE.items()
}


CLUSTER_TARGET_YEARS: tuple[int, ...] = (
    2000,
    2010,
    2020,
    2025,
)


ANOMALY_SCORE_WARNING_THRESHOLD = 0.75


def analytics_table_for_gold_table(gold_table: str) -> str:
    return f"analytics_{gold_table}"
