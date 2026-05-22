import pandas as pd

from gold.transforms import pivot_indicators, get_group_join, interpolate_numeric, add_completeness

_INDICATOR_MAP = {
    "rgdp_growth_yoy":      "rGDP_growth_YoY",
    "rolling_mean_5yr":     "rolling_mean_5yr",
    "gdp_growth_yoy":       "GDP_growth_YoY",
    "gdp_growth_trend_5yr": "GDP_growth_trend_5yr",
    "trend_deviation":      "trend_deviation",
    "gdp_pc_growth_gap":    "GDP_pc_growth_gap",
    "log_rgdp_pc_usd":      "log_rGDP_pc_USD",
}

_NO_INTERP = ["rGDP_growth_YoY"]


def build(silver: pd.DataFrame) -> pd.DataFrame:
    df = pivot_indicators(silver, _INDICATOR_MAP)

    df["rGDP_growth_YoY"] = df["rGDP_growth_YoY"].clip(-50, 50)

    groups = get_group_join(silver)[["country_code", "year", "income_group", "development_group"]]
    df = df.merge(groups, on=["country_code", "year"], how="left")

    df = interpolate_numeric(df, skip_cols=_NO_INTERP)
    df = add_completeness(df)
    return df.sort_values(["country_code", "year"]).reset_index(drop=True)