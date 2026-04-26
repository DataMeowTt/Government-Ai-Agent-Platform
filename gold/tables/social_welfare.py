import pandas as pd

from gold.io import load_to_postgres
from gold.transforms import pivot_indicators, get_group_join, interpolate_numeric, add_completeness

_INDICATOR_MAP = {
    "unemployment_total":      "unemployment_total",
    "unemployment_youth":      "unemployment_youth",
    "youth_unemployment_gap":  "youth_unemployment_gap",
    "youth_gap_ratio":         "youth_gap_ratio",
    "self_employed_total":     "self_employed_pct",
    "poverty_headcount_ratio": "poverty_headcount",
    "poverty_change_5yr":      "poverty_change_5yr",
    "urban_population":        "urban_pop_pct",
    "urban_population_growth": "urban_pop_growth",
    "population_density":      "pop_density",
    "log_pop_density":         "log_pop_density",
    "population_growth":       "pop_growth",
    "hcons_gdp":               "hcons_share",
    "hcons_growth":            "hcons_growth",
    "trade_gdp":               "trade_pct_gdp",
}


def build(silver: pd.DataFrame) -> pd.DataFrame:
    df = pivot_indicators(silver, _INDICATOR_MAP)

    groups = get_group_join(silver)[["country_code", "year", "income_group", "development_group"]]
    df = df.merge(groups, on=["country_code", "year"], how="left")

    df = interpolate_numeric(df)
    df = add_completeness(df)
    return df.sort_values(["country_code", "year"]).reset_index(drop=True)


def run(silver: pd.DataFrame, engine) -> None:
    load_to_postgres(build(silver), "gold_social_welfare", engine)
