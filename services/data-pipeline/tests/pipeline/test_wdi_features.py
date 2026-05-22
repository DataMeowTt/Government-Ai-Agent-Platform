import pytest

from pipeline.wdi.features import compute_wdi_features


def test_youth_unemployment_gap(spark):
    schema = (
        "country_code STRING, country STRING, year INT, source STRING,"
        " unemployment_total DOUBLE, unemployment_youth DOUBLE,"
        " inflation_consumer_prices DOUBLE, inflation_gdp_deflator DOUBLE,"
        " poverty_headcount_ratio DOUBLE, gdp_growth DOUBLE, gdp_per_capita_growth DOUBLE,"
        " population_density DOUBLE"
    )
    df = spark.createDataFrame([
        ("USA", "United States", 2000, "wdi", 5.0, 12.0, 2.0, 1.5, 10.0, 3.0, 2.5, 40.0),
    ], schema=schema)
    result = compute_wdi_features(df)
    row = result.collect()[0]
    assert row["youth_unemployment_gap"] == pytest.approx(12.0 - 5.0)


def test_gdp_pc_growth_gap(spark):
    schema = (
        "country_code STRING, country STRING, year INT, source STRING,"
        " unemployment_total DOUBLE, unemployment_youth DOUBLE,"
        " inflation_consumer_prices DOUBLE, inflation_gdp_deflator DOUBLE,"
        " poverty_headcount_ratio DOUBLE, gdp_growth DOUBLE, gdp_per_capita_growth DOUBLE,"
        " population_density DOUBLE"
    )
    df = spark.createDataFrame([
        ("USA", "United States", 2000, "wdi", 5.0, 12.0, 2.0, 1.5, 10.0, 3.0, 2.0, 40.0),
    ], schema=schema)
    result = compute_wdi_features(df)
    row = result.collect()[0]
    assert row["gdp_pc_growth_gap"] == pytest.approx(3.0 - 2.0)


def test_log_pop_density_non_negative(spark):
    schema = (
        "country_code STRING, country STRING, year INT, source STRING,"
        " unemployment_total DOUBLE, unemployment_youth DOUBLE,"
        " inflation_consumer_prices DOUBLE, inflation_gdp_deflator DOUBLE,"
        " poverty_headcount_ratio DOUBLE, gdp_growth DOUBLE, gdp_per_capita_growth DOUBLE,"
        " population_density DOUBLE"
    )
    df = spark.createDataFrame([
        ("USA", "United States", 2000, "wdi", 5.0, 12.0, 2.0, 1.5, 10.0, 3.0, 2.0, 100.0),
    ], schema=schema)
    result = compute_wdi_features(df)
    row = result.collect()[0]
    assert row["log_pop_density"] > 0
