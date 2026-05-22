import pytest

from pipeline.macro.features import compute_macro_features


def _make_df(spark, rows):
    schema = (
        "country_code STRING, country STRING, year INT, source STRING,"
        " gdp_value DOUBLE, gfcf_value DOUBLE, gni_value DOUBLE,"
        " agri_va DOUBLE, manuf_va DOUBLE, va_foodbev DOUBLE, flag_score DOUBLE"
    )
    return spark.createDataFrame(rows, schema=schema)


def test_decade_computed_correctly(spark):
    rows = [
        ("USA", "United States", 1985, "macro", 1000.0, 200.0, 950.0, 50.0, 100.0, 30.0, 0.0),
        ("USA", "United States", 2003, "macro", 1100.0, 210.0, 1000.0, 48.0, 105.0, 32.0, 0.0),
    ]
    df = _make_df(spark, rows)
    result = compute_macro_features(df)
    rows_out = {r["year"]: r for r in result.collect()}
    assert rows_out[1985]["decade"] == pytest.approx(1980.0)
    assert rows_out[2003]["decade"] == pytest.approx(2000.0)


def test_gfcf_to_gdp(spark):
    rows = [
        ("USA", "United States", 2000, "macro", 1000.0, 250.0, 950.0, 50.0, 100.0, 30.0, 0.0),
    ]
    df = _make_df(spark, rows)
    result = compute_macro_features(df)
    row = result.collect()[0]
    assert row["gfcf_to_gdp"] == pytest.approx(250.0 / 1000.0 * 100)


def test_food_bev_share_manuf(spark):
    rows = [
        ("USA", "United States", 2000, "macro", 1000.0, 250.0, 950.0, 50.0, 200.0, 50.0, 0.0),
    ]
    df = _make_df(spark, rows)
    result = compute_macro_features(df)
    row = result.collect()[0]
    assert row["food_bev_share_manuf"] == pytest.approx(50.0 / 200.0 * 100)


def test_gdp_growth_yoy(spark):
    rows = [
        ("USA", "United States", 2000, "macro", 1000.0, 200.0, 950.0, 50.0, 100.0, 30.0, 0.0),
        ("USA", "United States", 2001, "macro", 1050.0, 210.0, 990.0, 48.0, 105.0, 31.0, 0.0),
    ]
    df = _make_df(spark, rows)
    result = compute_macro_features(df)
    rows_out = {r["year"]: r for r in result.collect()}
    expected = (1050.0 - 1000.0) / 1000.0 * 100
    assert rows_out[2001]["gdp_growth_yoy"] == pytest.approx(expected)
