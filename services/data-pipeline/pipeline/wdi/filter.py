from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from config.countries import ALLOWED_ISO3

ALLOWED_INDICATORS = {
    "Unemployment, total (% of total labor force) (modeled ILO estimate)",
    "Unemployment, youth total (% of total labor force ages 15-24) (modeled ILO estimate)",
    "Self-employed, total (% of total employment) (modeled ILO estimate)",
    "Urban population (% of total population)",
    "Urban population growth (annual %)",
    "Population density (people per sq. km of land area)",
    "Population growth (annual %)",
    "Inflation, consumer prices (annual %)",
    "Inflation, GDP deflator (annual %)",
    "Poverty headcount ratio at $3.00 a day (2021 PPP) (% of population)",
    "Trade (% of GDP)",
    "Imports of goods and services (current US$)",
    "Exports of goods and services (% of GDP)",
    "Tax revenue (% of GDP)",
    "GDP (current US$)",
    "GDP growth (annual %)",
    "GDP per capita (current US$)",
    "GDP per capita growth (annual %)",
}


def filter_by_country(df: DataFrame) -> DataFrame:
    return df.filter(F.col("Country Code").isin(list(ALLOWED_ISO3)))


def filter_by_indicator(df: DataFrame) -> DataFrame:
    return df.filter(F.col("Indicator Name").isin(list(ALLOWED_INDICATORS)))


def _validate_unemployment(df: DataFrame) -> DataFrame:
    for col in ("unemployment_total", "unemployment_youth"):
        df = df.withColumn(
            col,
            F.when((F.col(col) < 0) | (F.col(col) > 100), F.lit(None)).otherwise(F.col(col)),
        )
    return df


def _validate_gdp(df: DataFrame) -> DataFrame:
    for col in ("gdp", "gdp_per_capita"):
        df = df.withColumn(
            col,
            F.when(F.col(col) < 0, F.lit(None)).otherwise(F.col(col)),
        )
    return df


def _validate_inflation(df: DataFrame) -> DataFrame:
    for col in ("inflation_consumer_prices", "inflation_gdp_deflator"):
        df = df.withColumn(
            col,
            F.when(F.abs(F.col(col)) > 1000, F.lit(None)).otherwise(F.col(col)),
        )
    return df


def validate_all(df: DataFrame) -> DataFrame:
    df = _validate_unemployment(df)
    df = _validate_gdp(df)
    df = _validate_inflation(df)
    return df.dropDuplicates(["country_code", "year"])
