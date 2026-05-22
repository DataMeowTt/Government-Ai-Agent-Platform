import pandas as pd
import pytest

from gold.transforms import add_completeness, interpolate_numeric, apply_source_precedence


def test_add_completeness_all_present():
    df = pd.DataFrame({
        "country_code": ["USA"],
        "country":      ["United States"],
        "year":         [2000],
        "gdp":          [1.0],
        "infl":         [2.0],
    })
    result = add_completeness(df)
    assert result["completeness_score"].iloc[0] == pytest.approx(1.0)


def test_add_completeness_half_missing():
    df = pd.DataFrame({
        "country_code": ["USA"],
        "country":      ["United States"],
        "year":         [2000],
        "gdp":          [None],
        "infl":         [2.0],
    })
    result = add_completeness(df)
    assert result["completeness_score"].iloc[0] == pytest.approx(0.5)


def test_add_completeness_score_in_range():
    df = pd.DataFrame({
        "country_code": ["USA", "BRA"],
        "country":      ["United States", "Brazil"],
        "year":         [2000, 2000],
        "a":            [1.0, None],
        "b":            [None, None],
    })
    result = add_completeness(df)
    assert result["completeness_score"].between(0.0, 1.0).all()


def test_interpolate_numeric_fills_gaps():
    df = pd.DataFrame({
        "country_code": ["USA"] * 4,
        "country":      ["United States"] * 4,
        "year":         [2000, 2001, 2002, 2003],
        "gdp":          [1.0, None, None, 4.0],
    })
    result = interpolate_numeric(df)
    assert result["gdp"].notna().all()


def test_interpolate_numeric_skips_excluded_cols():
    df = pd.DataFrame({
        "country_code": ["USA"] * 3,
        "country":      ["United States"] * 3,
        "year":         [2000, 2001, 2002],
        "crisis_any":   [1.0, None, 0.0],
        "gdp":          [1.0, None, 3.0],
    })
    result = interpolate_numeric(df)
    # crisis_any is in NO_INTERPOLATE, so its null must remain
    assert pd.isna(result["crisis_any"].iloc[1])
    # gdp is not excluded, so it should be filled
    assert result["gdp"].notna().all()


def test_apply_source_precedence_picks_gmd_over_wdi():
    silver = pd.DataFrame({
        "country_code": ["USA", "USA"],
        "country":      ["United States", "United States"],
        "year":         [2000, 2000],
        "indicator":    ["rgdp_growth_yoy", "rgdp_growth_yoy"],
        "value":        [2.5, 3.0],
        "source":       ["wdi", "gmd"],
    })
    result = apply_source_precedence(silver, "rgdp_growth_yoy")
    assert len(result) == 1
    assert result.iloc[0]["value"] == 2.5  # gmd has rank 0 (highest precedence)
