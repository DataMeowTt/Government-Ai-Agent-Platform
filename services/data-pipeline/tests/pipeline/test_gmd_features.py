import pytest

from pipeline.gmd.features import compute_gmd_features


def _make_df(spark, rows):
    schema = (
        "country_code STRING, country STRING, year INT, source STRING,"
        " rgdp DOUBLE, rgdp_pc_usd DOUBLE, hcons_gdp DOUBLE, govdebt_gdp DOUBLE,"
        " govtax_gdp DOUBLE, sov_debt_crisis DOUBLE, currency_crisis DOUBLE,"
        " banking_crisis DOUBLE, exports_gdp DOUBLE, imports_gdp DOUBLE,"
        " govrev_gdp DOUBLE, govexp_gdp DOUBLE, ltrate DOUBLE, infl DOUBLE,"
        " reer DOUBLE, hcons_usd DOUBLE, income_group STRING"
    )
    return spark.createDataFrame(rows, schema=schema)


def test_rgdp_growth_yoy(spark):
    rows = [
        ("USA", "United States", 2000, "gmd", 1000.0, 50000.0, 60.0, 80.0,
         15.0, 0.0, 0.0, 0.0, 25.0, 20.0, 30.0, 35.0, 3.0, 2.0, 100.0, 800.0, "High income"),
        ("USA", "United States", 2001, "gmd", 1050.0, 52000.0, 61.0, 82.0,
         15.5, 0.0, 0.0, 0.0, 26.0, 21.0, 31.0, 36.0, 3.1, 2.1, 102.0, 820.0, "High income"),
    ]
    df = _make_df(spark, rows)
    result = compute_gmd_features(df)
    row_2001 = [r for r in result.collect() if r["year"] == 2001][0]
    expected = (1050.0 - 1000.0) / 1000.0 * 100
    assert row_2001["rgdp_growth_yoy"] == pytest.approx(expected)


def test_crisis_composite_is_sum_of_flags(spark):
    rows = [
        ("BRA", "Brazil", 2000, "gmd", 500.0, 8000.0, 55.0, 70.0,
         12.0, 1.0, 1.0, 0.0, 20.0, 18.0, 25.0, 30.0, 8.0, 5.0, 90.0, 400.0, "Lower middle income"),
    ]
    df = _make_df(spark, rows)
    result = compute_gmd_features(df)
    row = result.collect()[0]
    # sov_debt_crisis + currency_crisis + banking_crisis = 1 + 1 + 0 = 2
    assert row["crisis_composite"] == pytest.approx(2.0)


def test_fiscal_balance_is_rev_minus_exp(spark):
    rows = [
        ("BRA", "Brazil", 2000, "gmd", 500.0, 8000.0, 55.0, 70.0,
         12.0, 0.0, 0.0, 0.0, 20.0, 18.0, 28.0, 32.0, 8.0, 5.0, 90.0, 400.0, "Lower middle income"),
    ]
    df = _make_df(spark, rows)
    result = compute_gmd_features(df)
    row = result.collect()[0]
    assert row["fiscal_balance_gdp"] == pytest.approx(28.0 - 32.0)


def test_development_group_thresholds(spark):
    rows = [
        ("A", "A", 2000, "gmd", 1.0, 500.0,  0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "Low income"),
        ("B", "B", 2000, "gmd", 1.0, 2000.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "Lower middle income"),
        ("C", "C", 2000, "gmd", 1.0, 8000.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "Upper middle income"),
        ("D", "D", 2000, "gmd", 1.0, 20000.0,0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "High income"),
    ]
    df = _make_df(spark, rows)
    result = compute_gmd_features(df)
    groups = {r["country_code"]: r["development_group"] for r in result.collect()}
    assert groups["A"] == 0.0
    assert groups["B"] == 1.0
    assert groups["C"] == 2.0
    assert groups["D"] == 3.0
