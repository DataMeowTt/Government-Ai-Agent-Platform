from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from config.countries import COUNTRY_ISO3_MAP
from pipeline.schema.processed_schema import (
    COL_COUNTRY_CODE, COL_COUNTRY, COL_YEAR, COL_SOURCE,
    SOURCE_MACRO,
)

ITEM_CODE_MAP = {
    "22008": "gdp_value",
    "22015": "gfcf_value",
    "22011": "gni_value",
    "22016": "agri_va",
    "22075": "manuf_va",
    "22076": "va_foodbev",
}

_ID_COLS = frozenset({COL_COUNTRY_CODE, COL_COUNTRY, COL_YEAR, COL_SOURCE})


def _encode_flag(df: DataFrame) -> DataFrame:
    return df.withColumn(
        "flag_score",
        F.when(F.col("Flag").isNull() | (F.col("Flag") == ""), F.lit(0.0))
        .when(F.col("Flag") == "E",  F.lit(1.0))
        .when(F.col("Flag") == "X",  F.lit(2.0))
        .otherwise(F.lit(3.0)),
    )


def pivot_to_wide(df: DataFrame) -> DataFrame:
    item_map_expr    = F.create_map([F.lit(x) for pair in ITEM_CODE_MAP.items()    for x in pair])
    country_map_expr = F.create_map([F.lit(x) for pair in COUNTRY_ISO3_MAP.items() for x in pair])

    df = _encode_flag(df)

    flag_agg = (
        df.groupBy("Area", "Year")
        .agg(F.max("flag_score").alias("flag_score"))
    )

    df = df.withColumn("indicator", item_map_expr[F.col("Item Code")])
    wide = (
        df.groupBy("Area", "Year")
        .pivot("indicator", list(ITEM_CODE_MAP.values()))
        .agg(F.first(F.col("Value").cast("double")))
        .join(flag_agg, on=["Area", "Year"], how="left")
    )

    return (
        wide
        .withColumn(COL_COUNTRY_CODE, country_map_expr[F.col("Area")])
        .withColumn(COL_COUNTRY,      F.col("Area"))
        .withColumn(COL_SOURCE,       F.lit(SOURCE_MACRO))
        .drop("Area")
        .withColumnRenamed("Year", COL_YEAR)
        .withColumn(COL_YEAR, F.col(COL_YEAR).cast("int"))
    )


def unpivot_all(df: DataFrame) -> DataFrame:
    value_cols = [c for c in df.columns if c not in _ID_COLS]
    stack_expr = "stack({n}, {pairs}) as (indicator, value)".format(
        n=len(value_cols),
        pairs=", ".join([f"'{c}', `{c}`" for c in value_cols]),
    )
    return df.select(COL_COUNTRY_CODE, COL_COUNTRY, COL_YEAR, F.expr(stack_expr), COL_SOURCE)
