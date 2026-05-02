ANALYTICS_TABLES_INDICATORS: dict[str, list[str]] = {
    "gold_growth_dynamics": [
        "rGDP_growth_YoY",
        "GDP_growth_YoY",
        "trend_deviation",
        "GDP_pc_growth_gap",
        "rolling_mean_5yr",
    ],
    "gold_fiscal_monetary": [
        "govdebt_GDP",
        "fiscal_balance_GDP",
        "real_interest_rate",
        "inflation_gap",
        "inflation_cpi",
        "tax_revenue_pct_GDP",
    ],
    "gold_crisis_risk": [
        "REER_deviation",
        "spending_efficiency",
    ],
    "gold_social_welfare": [
        "poverty_headcount",
        "poverty_change_5yr",
        "hcons_growth",
        "unemployment_total",
        "youth_unemployment_gap",
    ],
    "gold_structural_composition": [
        "GFCF_to_GDP",
        "GNI_to_GDP",
        "agri_va_share",
        "manuf_va_share",
        "food_bev_share_manuf",
    ],
}


ANALYTICS_SUFFIXES: tuple[str, ...] = (
    "actual",
    "trend",
    "residual",
    "slope",
    "intercept",
    "r2",
    "anomaly_score",
)


CLUSTER_INDICATORS: tuple[str, ...] = (
    "agri_va_share",
    "manuf_va_share",
    "GFCF_to_GDP",
    "GNI_to_GDP",
    "poverty_headcount",
    "urban_pop_pct",
    "unemployment_total",
)


CLUSTER_TARGET_YEARS: tuple[int, ...] = (
    2000,
    2010,
    2020,
    2022,
)


def analytics_table_for_gold_table(gold_table: str) -> str:
    return f"analytics_{gold_table}"


def get_analytics_table_for_indicator(indicator_code: str) -> str | None:
    for gold_table, indicators in ANALYTICS_TABLES_INDICATORS.items():
        if indicator_code in indicators:
            return analytics_table_for_gold_table(gold_table)

    return None


def indicator_has_analytics(indicator_code: str) -> bool:
    return get_analytics_table_for_indicator(indicator_code) is not None


def get_analytics_columns(indicator_code: str) -> list[str]:
    if not indicator_has_analytics(indicator_code):
        return []

    return [f"{indicator_code}_{suffix}" for suffix in ANALYTICS_SUFFIXES]


def indicator_supports_anomaly(indicator_code: str) -> bool:
    return indicator_has_analytics(indicator_code)


def indicator_supports_trend(indicator_code: str) -> bool:
    return indicator_has_analytics(indicator_code)


def indicator_used_for_cluster(indicator_code: str) -> bool:
    return indicator_code in CLUSTER_INDICATORS


def get_indicator_analytics_metadata(indicator_code: str) -> dict:
    analytics_table = get_analytics_table_for_indicator(indicator_code)

    return {
        "has_analytics": analytics_table is not None,
        "analytics_table": analytics_table,
        "analytics_columns": get_analytics_columns(indicator_code),
        "supports_trend": indicator_supports_trend(indicator_code),
        "supports_anomaly": indicator_supports_anomaly(indicator_code),
        "used_for_cluster": indicator_used_for_cluster(indicator_code),
    }