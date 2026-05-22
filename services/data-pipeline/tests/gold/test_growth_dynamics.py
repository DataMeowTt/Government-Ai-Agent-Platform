import pytest

from gold.tables.growth_dynamics import build


def test_build_returns_expected_columns(sample_silver):
    df = build(sample_silver)
    expected = {
        "country_code", "country", "year",
        "rGDP_growth_YoY", "rolling_mean_5yr", "GDP_growth_YoY",
        "GDP_growth_trend_5yr", "trend_deviation", "GDP_pc_growth_gap",
        "log_rGDP_pc_USD", "income_group", "development_group", "completeness_score",
    }
    assert expected.issubset(set(df.columns))


def test_build_sorted_by_country_year(sample_silver):
    df = build(sample_silver)
    pairs = list(zip(df["country_code"], df["year"]))
    assert pairs == sorted(pairs)


def test_build_completeness_in_range(sample_silver):
    df = build(sample_silver)
    assert df["completeness_score"].between(0.0, 1.0).all()


def test_build_rgdp_growth_clipped(sample_silver):
    import pandas as pd
    extra = pd.DataFrame({
        "country_code": ["USA"],
        "country":      ["United States"],
        "year":         [2005],
        "indicator":    ["rgdp_growth_yoy"],
        "value":        [200.0],   # should be clipped to 50
        "source":       ["gmd"],
    })
    silver = pd.concat([sample_silver, extra], ignore_index=True)
    df = build(silver)
    val = df.loc[(df["country_code"] == "USA") & (df["year"] == 2005), "rGDP_growth_YoY"]
    if not val.empty:
        assert val.iloc[0] <= 50.0
