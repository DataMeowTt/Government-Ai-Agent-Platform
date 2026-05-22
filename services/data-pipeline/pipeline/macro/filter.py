from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from config.countries import COUNTRY_ISO3_MAP

_ALLOWED_AREAS  = frozenset(COUNTRY_ISO3_MAP.keys())
_ALLOWED_ITEMS  = {"22008", "22015", "22011", "22016", "22075", "22076"}
_YEAR_MIN, _YEAR_MAX = 1980, 2025


def filter_by_area(df: DataFrame) -> DataFrame:
    return df.filter(F.col("Area").isin(list(_ALLOWED_AREAS)))


def filter_by_year(df: DataFrame) -> DataFrame:
    return df.filter(F.col("Year").cast("int").between(_YEAR_MIN, _YEAR_MAX))


def filter_by_item(df: DataFrame) -> DataFrame:
    return df.filter(F.col("Item Code").isin(list(_ALLOWED_ITEMS)))


def _validate_gdp(df: DataFrame) -> DataFrame:
    for col in ("gdp_value", "gfcf_value", "gni_value", "agri_va", "manuf_va", "va_foodbev"):
        df = df.withColumn(col, F.when(F.col(col) < 0, F.lit(None)).otherwise(F.col(col)))
    return df


def _validate_shares(df: DataFrame) -> DataFrame:
    for col in ("gfcf_to_gdp", "agri_va_share", "manuf_va_share"):
        df = df.withColumn(
            col,
            F.when((F.col(col) < 0) | (F.col(col) > 200), F.lit(None)).otherwise(F.col(col)),
        )
    df = df.withColumn(
        "food_bev_share_manuf",
        F.when(
            (F.col("food_bev_share_manuf") < 0) | (F.col("food_bev_share_manuf") > 100),
            F.lit(None),
        ).otherwise(F.col("food_bev_share_manuf")),
    )
    df = df.withColumn(
        "gni_to_gdp",
        F.when(
            (F.col("gni_to_gdp") < 0.5) | (F.col("gni_to_gdp") > 2.0), F.lit(None),
        ).otherwise(F.col("gni_to_gdp")),
    )
    return df


def _validate_growth(df: DataFrame) -> DataFrame:
    return df.withColumn(
        "gdp_growth_yoy",
        F.when(F.abs(F.col("gdp_growth_yoy")) > 100, F.lit(None))
        .otherwise(F.col("gdp_growth_yoy")),
    )


def _validate_flag_score(df: DataFrame) -> DataFrame:
    return df.withColumn(
        "flag_score",
        F.when(F.col("flag_score").isin(0.0, 1.0, 2.0, 3.0), F.col("flag_score"))
        .otherwise(F.lit(None)),
    )


def validate_all(df: DataFrame) -> DataFrame:
    df = _validate_gdp(df)
    df = _validate_shares(df)
    df = _validate_growth(df)
    df = _validate_flag_score(df)
    return df.dropDuplicates(["country_code", "year"])
