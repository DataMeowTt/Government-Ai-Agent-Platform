from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from config.countries import ALLOWED_ISO3

_YEAR_MIN = 1980
_YEAR_MAX = 2025


def filter_by_country(df: DataFrame) -> DataFrame:
    return df.filter(F.col("ISO3").isin(list(ALLOWED_ISO3)))


def filter_by_year(df: DataFrame) -> DataFrame:
    return df.filter(F.col("year").between(_YEAR_MIN, _YEAR_MAX))


def _validate_rgdp(df: DataFrame) -> DataFrame:
    for col in ("rgdp", "rgdp_pc_usd"):
        df = df.withColumn(col, F.when(F.col(col) < 0, F.lit(None)).otherwise(F.col(col)))
    return df


def _validate_inflation(df: DataFrame) -> DataFrame:
    return df.withColumn(
        "infl",
        F.when(F.abs(F.col("infl")) > 1000, F.lit(None)).otherwise(F.col("infl")),
    )


def _validate_rates(df: DataFrame) -> DataFrame:
    return df.withColumn(
        "ltrate",
        F.when(
            (F.col("ltrate") < -20) | (F.col("ltrate") > 200), F.lit(None),
        ).otherwise(F.col("ltrate")),
    )


def _validate_debt(df: DataFrame) -> DataFrame:
    return df.withColumn(
        "govdebt_gdp",
        F.when(F.col("govdebt_gdp") > 500, F.lit(None)).otherwise(F.col("govdebt_gdp")),
    )


def _validate_crisis_flags(df: DataFrame) -> DataFrame:
    for col in ("sov_debt_crisis", "currency_crisis", "banking_crisis"):
        df = df.withColumn(
            col,
            F.when(F.col(col).isin(0.0, 1.0), F.col(col)).otherwise(F.lit(None)),
        )
    return df


def validate_all(df: DataFrame) -> DataFrame:
    df = _validate_rgdp(df)
    df = _validate_inflation(df)
    df = _validate_rates(df)
    df = _validate_debt(df)
    df = _validate_crisis_flags(df)
    return df.dropDuplicates(["country_code", "year"])
