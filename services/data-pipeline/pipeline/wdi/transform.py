from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from pipeline.schema.processed_schema import (
    COL_COUNTRY_CODE, COL_COUNTRY, COL_YEAR, COL_INDICATOR, COL_VALUE, COL_SOURCE,
    SOURCE_WDI,
)

YEAR_COLS = [str(y) for y in range(1980, 2026)]

_ID_COLS = {COL_COUNTRY_CODE, COL_COUNTRY, COL_YEAR, COL_SOURCE}

INDICATOR_CODE_MAP = {
    "Unemployment, total (% of total labor force) (modeled ILO estimate)":                   "unemployment_total",
    "Unemployment, youth total (% of total labor force ages 15-24) (modeled ILO estimate)":  "unemployment_youth",
    "Self-employed, total (% of total employment) (modeled ILO estimate)":                   "self_employed_total",
    "Urban population (% of total population)":                                              "urban_population",
    "Urban population growth (annual %)":                                                    "urban_population_growth",
    "Population density (people per sq. km of land area)":                                   "population_density",
    "Population growth (annual %)":                                                          "population_growth",
    "Inflation, consumer prices (annual %)":                                                 "inflation_consumer_prices",
    "Inflation, GDP deflator (annual %)":                                                    "inflation_gdp_deflator",
    "Poverty headcount ratio at $3.00 a day (2021 PPP) (% of population)":                  "poverty_headcount_ratio",
    "Trade (% of GDP)":                                                                      "trade_gdp",
    "Imports of goods and services (current US$)":                                           "imports_goods_services",
    "Exports of goods and services (% of GDP)":                                              "exports_goods_services",
    "Tax revenue (% of GDP)":                                                                "tax_revenue_gdp",
    "GDP (current US$)":                                                                     "gdp",
    "GDP growth (annual %)":                                                                 "gdp_growth",
    "GDP per capita (current US$)":                                                          "gdp_per_capita",
    "GDP per capita growth (annual %)":                                                      "gdp_per_capita_growth",
}


def flatten_years(df: DataFrame) -> DataFrame:
    unpivoted = df.unpivot(
        ids=["Country Name", "Country Code", "Indicator Name"],
        values=YEAR_COLS,
        variableColumnName=COL_YEAR,
        valueColumnName=COL_VALUE,
    )
    return unpivoted.select(
        F.col("Country Code").alias(COL_COUNTRY_CODE),
        F.col("Country Name").alias(COL_COUNTRY),
        F.col(COL_YEAR).cast("int"),
        F.col("Indicator Name").alias(COL_INDICATOR),
        F.col(COL_VALUE).cast("double"),
        F.lit(SOURCE_WDI).alias(COL_SOURCE),
    )


def map_indicator_codes(df: DataFrame) -> DataFrame:
    mapping_expr = F.create_map([F.lit(x) for pair in INDICATOR_CODE_MAP.items() for x in pair])
    return df.withColumn(COL_INDICATOR, mapping_expr[F.col(COL_INDICATOR)])


def unpivot_all(wide: DataFrame) -> DataFrame:
    value_cols = [c for c in wide.columns if c not in _ID_COLS]
    stack_expr = "stack({n}, {pairs}) as (indicator, value)".format(
        n=len(value_cols),
        pairs=", ".join([f"'{c}', `{c}`" for c in value_cols]),
    )
    return wide.select(
        COL_COUNTRY_CODE, COL_COUNTRY, COL_YEAR, F.expr(stack_expr), COL_SOURCE,
    )
