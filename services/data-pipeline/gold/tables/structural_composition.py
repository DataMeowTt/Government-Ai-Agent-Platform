import pandas as pd

from gold.transforms import pivot_indicators, get_group_join, interpolate_numeric, add_completeness

_INDICATOR_MAP = {
    "decade":               "decade",
    "gdp_value":            "GDP_value",
    "gfcf_value":           "GFCF_value",
    "gni_value":            "GNI_value",
    "agri_va":              "Agri_VA",
    "manuf_va":             "Manuf_VA",
    "va_foodbev":           "VA_FoodBev",
    "gfcf_to_gdp":          "GFCF_to_GDP",
    "gni_to_gdp":           "GNI_to_GDP",
    "agri_va_share":        "agri_va_share",
    "manuf_va_share":       "manuf_va_share",
    "food_bev_share_manuf": "food_bev_share_manuf",
    "gdp_growth_yoy":       "GDP_growth_YoY",
    "flag_score":           "flag_score",
}

_NO_INTERP = ["flag_score", "decade"]


def build(silver: pd.DataFrame) -> pd.DataFrame:
    df = pivot_indicators(silver, _INDICATOR_MAP)

    p99 = df["food_bev_share_manuf"].quantile(0.99)
    df["food_bev_share_manuf"] = df["food_bev_share_manuf"].clip(upper=p99)

    groups = get_group_join(silver)[["country_code", "year", "income_group", "development_group"]]
    df = df.merge(groups, on=["country_code", "year"], how="left")

    df = interpolate_numeric(df, skip_cols=_NO_INTERP)
    df = add_completeness(df)
    return df.sort_values(["country_code", "year"]).reset_index(drop=True)
