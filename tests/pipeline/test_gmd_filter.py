import pytest

from pipeline.gmd.filter import filter_by_country, filter_by_year, validate_all


def test_filter_by_country_keeps_allowed(spark):
    df = spark.createDataFrame([
        ("USA", "United States", 2000),
        ("ZZZ", "Unknown",       2000),
    ], ["ISO3", "countryname", "year"])
    result = filter_by_country(df)
    codes = [r["ISO3"] for r in result.collect()]
    assert "USA" in codes
    assert "ZZZ" not in codes


def test_filter_by_year_range(spark):
    df = spark.createDataFrame([
        ("USA", 1970),
        ("USA", 2000),
        ("USA", 2030),
    ], ["ISO3", "year"])
    result = filter_by_year(df)
    years = [r["year"] for r in result.collect()]
    assert 2000 in years
    assert 1970 not in years
    assert 2030 not in years


def test_validate_debt_clips_extreme(spark):
    df = spark.createDataFrame([
        ("USA", 2000, 50.0),
        ("USA", 2001, 600.0),  # above 500 threshold
    ], ["country_code", "year", "govdebt_gdp"])
    result = validate_all(df)
    rows = {r["year"]: r for r in result.collect()}
    assert rows[2000]["govdebt_gdp"] == 50.0
    assert rows[2001]["govdebt_gdp"] is None


def test_validate_crisis_flags_binary(spark):
    df = spark.createDataFrame([
        ("USA", 2000, 0.0, 1.0, 0.0),
        ("USA", 2001, 5.0, 1.0, 0.0),   # sov_debt_crisis=5 is invalid
    ], ["country_code", "year", "sov_debt_crisis", "currency_crisis", "banking_crisis"])
    result = validate_all(df)
    rows = {r["year"]: r for r in result.collect()}
    assert rows[2000]["sov_debt_crisis"] == 0.0
    assert rows[2001]["sov_debt_crisis"] is None
