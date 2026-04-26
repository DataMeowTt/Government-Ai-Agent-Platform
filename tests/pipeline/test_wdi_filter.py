import pytest
from pyspark.sql import Row

from pipeline.wdi.filter import filter_by_country, filter_by_indicator, validate_all


def test_filter_by_country_keeps_allowed(spark):
    df = spark.createDataFrame([
        Row(**{"Country Code": "USA", "Country Name": "United States"}),
        Row(**{"Country Code": "ZZZ", "Country Name": "Unknown"}),
    ])
    result = filter_by_country(df)
    codes = [r["Country Code"] for r in result.collect()]
    assert "USA" in codes
    assert "ZZZ" not in codes


def test_filter_by_country_drops_all_unknown(spark):
    df = spark.createDataFrame([
        Row(**{"Country Code": "XYZ", "Country Name": "Fake"}),
    ])
    assert filter_by_country(df).count() == 0


def test_filter_by_indicator_keeps_allowed(spark):
    df = spark.createDataFrame([
        Row(**{"Indicator Name": "GDP growth (annual %)"}),
        Row(**{"Indicator Name": "Some random indicator"}),
    ])
    result = filter_by_indicator(df)
    names = [r["Indicator Name"] for r in result.collect()]
    assert "GDP growth (annual %)" in names
    assert "Some random indicator" not in names


def test_validate_all_clips_unemployment(spark):
    schema = "country_code STRING, year INT, unemployment_total DOUBLE, unemployment_youth DOUBLE"
    df = spark.createDataFrame([
        ("USA", 2000, 150.0, 5.0),   # unemployment_total out of range
        ("USA", 2001, 5.0,  -1.0),   # unemployment_youth out of range
        ("USA", 2002, 5.0,  10.0),   # both valid
    ], schema=schema)
    result = validate_all(df)
    rows = {r["year"]: r for r in result.collect()}
    assert rows[2000]["unemployment_total"] is None
    assert rows[2001]["unemployment_youth"] is None
    assert rows[2002]["unemployment_total"] == 5.0


def test_validate_all_clips_inflation(spark):
    schema = "country_code STRING, year INT, inflation_consumer_prices DOUBLE, inflation_gdp_deflator DOUBLE"
    df = spark.createDataFrame([
        ("USA", 2000, 2000.0, 2.0),   # cpi out of range
        ("USA", 2001, 3.0,    2.0),   # valid
    ], schema=schema)
    result = validate_all(df)
    rows = {r["year"]: r for r in result.collect()}
    assert rows[2000]["inflation_consumer_prices"] is None
    assert rows[2001]["inflation_consumer_prices"] == 3.0


def test_validate_all_deduplicates(spark):
    schema = "country_code STRING, year INT, gdp DOUBLE"
    df = spark.createDataFrame([
        ("USA", 2000, 1.0),
        ("USA", 2000, 2.0),  # duplicate
    ], schema=schema)
    assert validate_all(df).count() == 1
