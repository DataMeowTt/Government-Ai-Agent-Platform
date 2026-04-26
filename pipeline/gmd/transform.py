from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from pipeline.schema.processed_schema import (
    COL_COUNTRY_CODE, COL_COUNTRY, COL_YEAR, COL_SOURCE,
    SOURCE_GMD,
)

# Columns to select from raw GMD and their cleaned names.
NUMERIC_COLS = {
    "rGDP":          "rgdp",
    "rGDP_pc_USD":   "rgdp_pc_usd",
    "hcons_GDP":     "hcons_gdp",
    "govdebt_GDP":   "govdebt_gdp",
    "govtax_GDP":    "govtax_gdp",
    "SovDebtCrisis": "sov_debt_crisis",
    "CurrencyCrisis": "currency_crisis",
    "BankingCrisis": "banking_crisis",
    "exports_GDP":   "exports_gdp",
    "imports_GDP":   "imports_gdp",
    "govrev_GDP":    "govrev_gdp",
    "govexp_GDP":    "govexp_gdp",
    "ltrate":        "ltrate",
    "infl":          "infl",
    # Helper columns — used for feature computation only, not written to output.
    "REER":          "reer",
    "hcons_USD":     "hcons_usd",
}

STRING_COLS = {
    "income_group": "income_group",
}

_ID_COLS    = frozenset({COL_COUNTRY_CODE, COL_COUNTRY, COL_YEAR, COL_SOURCE})
_HELPER_COLS = frozenset({"reer", "hcons_usd", "income_group"})


def select_and_rename(df: DataFrame) -> DataFrame:
    raw_cols = (
        ["countryname", "ISO3", "year"]
        + list(NUMERIC_COLS.keys())
        + list(STRING_COLS.keys())
    )
    df = df.select(*raw_cols)

    for raw, clean in NUMERIC_COLS.items():
        df = df.withColumnRenamed(raw, clean).withColumn(clean, F.col(clean).cast("double"))

    return (
        df
        .withColumnRenamed("countryname", COL_COUNTRY)
        .withColumnRenamed("ISO3", COL_COUNTRY_CODE)
        .withColumn(COL_YEAR, F.col("year").cast("int"))
        .withColumn(COL_SOURCE, F.lit(SOURCE_GMD))
    )


def unpivot_all(df: DataFrame) -> DataFrame:
    skip = _ID_COLS | _HELPER_COLS
    value_cols = [c for c in df.columns if c not in skip]
    df = df.drop(*_HELPER_COLS)
    stack_expr = "stack({n}, {pairs}) as (indicator, value)".format(
        n=len(value_cols),
        pairs=", ".join([f"'{c}', `{c}`" for c in value_cols]),
    )
    return df.select(COL_COUNTRY_CODE, COL_COUNTRY, COL_YEAR, F.expr(stack_expr), COL_SOURCE)
