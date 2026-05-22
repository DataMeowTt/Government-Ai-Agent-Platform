import pandas as pd
import pytest


@pytest.fixture(scope="session")
def spark():
    from pyspark.sql import SparkSession
    session = (
        SparkSession.builder
        .master("local[1]")
        .appName("test")
        .config("spark.sql.shuffle.partitions", "1")
        .getOrCreate()
    )
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()


@pytest.fixture()
def sample_silver() -> pd.DataFrame:
    rows = [
        # growth indicators from GMD
        ("USA", "United States", 2000, "rgdp_growth_yoy",    2.5, "gmd"),
        ("USA", "United States", 2001, "rgdp_growth_yoy",    1.0, "gmd"),
        ("USA", "United States", 2000, "rolling_mean_5yr",   2.2, "gmd"),
        ("USA", "United States", 2001, "rolling_mean_5yr",   1.8, "gmd"),
        ("USA", "United States", 2000, "gdp_growth_yoy",     2.3, "macro"),
        ("USA", "United States", 2001, "gdp_growth_yoy",     1.1, "macro"),
        ("USA", "United States", 2000, "gdp_growth_trend_5yr", 2.1, "macro"),
        ("USA", "United States", 2001, "gdp_growth_trend_5yr", 1.9, "macro"),
        ("USA", "United States", 2000, "trend_deviation",    0.2, "macro"),
        ("USA", "United States", 2001, "trend_deviation",   -0.8, "macro"),
        ("USA", "United States", 2000, "gdp_pc_growth_gap",  0.1, "wdi"),
        ("USA", "United States", 2001, "gdp_pc_growth_gap",  0.3, "wdi"),
        ("USA", "United States", 2000, "log_rgdp_pc_usd",   10.5, "gmd"),
        ("USA", "United States", 2001, "log_rgdp_pc_usd",   10.6, "gmd"),
        # group metadata
        ("USA", "United States", 2000, "income_group_encoded", 3.0, "gmd"),
        ("USA", "United States", 2001, "income_group_encoded", 3.0, "gmd"),
        ("USA", "United States", 2000, "development_group",    3.0, "gmd"),
        ("USA", "United States", 2001, "development_group",    3.0, "gmd"),
        # crisis flags
        ("BRA", "Brazil",        2000, "sov_debt_crisis",   0.0, "gmd"),
        ("BRA", "Brazil",        2001, "sov_debt_crisis",   1.0, "gmd"),
        ("BRA", "Brazil",        2000, "currency_crisis",   1.0, "gmd"),
        ("BRA", "Brazil",        2001, "currency_crisis",   0.0, "gmd"),
        ("BRA", "Brazil",        2000, "banking_crisis",    0.0, "gmd"),
        ("BRA", "Brazil",        2001, "banking_crisis",    0.0, "gmd"),
        ("BRA", "Brazil",        2000, "crisis_composite",  1.0, "gmd"),
        ("BRA", "Brazil",        2001, "crisis_composite",  1.0, "gmd"),
        ("BRA", "Brazil",        2000, "crisis_any",        1.0, "gmd"),
        ("BRA", "Brazil",        2001, "crisis_any",        1.0, "gmd"),
        ("BRA", "Brazil",        2000, "REER_deviation",    5.0, "gmd"),
        ("BRA", "Brazil",        2001, "REER_deviation",   -2.0, "gmd"),
        ("BRA", "Brazil",        2000, "spending_efficiency", 0.3, "gmd"),
        ("BRA", "Brazil",        2001, "spending_efficiency", 0.2, "gmd"),
        ("BRA", "Brazil",        2000, "govdebt_gdp",       60.0, "gmd"),
        ("BRA", "Brazil",        2001, "govdebt_gdp",       65.0, "gmd"),
        ("BRA", "Brazil",        2000, "fiscal_balance_gdp", -3.0, "gmd"),
        ("BRA", "Brazil",        2001, "fiscal_balance_gdp", -4.0, "gmd"),
        ("BRA", "Brazil",        2000, "rgdp_growth_yoy",   1.5, "gmd"),
        ("BRA", "Brazil",        2001, "rgdp_growth_yoy",  -0.5, "gmd"),
        ("BRA", "Brazil",        2000, "income_group_encoded", 1.0, "gmd"),
        ("BRA", "Brazil",        2001, "income_group_encoded", 1.0, "gmd"),
        ("BRA", "Brazil",        2000, "development_group",  2.0, "gmd"),
        ("BRA", "Brazil",        2001, "development_group",  2.0, "gmd"),
    ]
    return pd.DataFrame(rows, columns=["country_code", "country", "year", "indicator", "value", "source"])
