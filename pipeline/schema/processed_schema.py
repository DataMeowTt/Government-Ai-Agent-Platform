from pyspark.sql.types import DoubleType, IntegerType, StringType, StructField, StructType

COL_COUNTRY_CODE = "country_code"
COL_COUNTRY      = "country"
COL_YEAR         = "year"
COL_INDICATOR    = "indicator"
COL_VALUE        = "value"
COL_SOURCE       = "source"

PROCESSED_SCHEMA = StructType([
    StructField(COL_COUNTRY_CODE, StringType(),  nullable=False),
    StructField(COL_COUNTRY,      StringType(),  nullable=False),
    StructField(COL_YEAR,         IntegerType(), nullable=False),
    StructField(COL_INDICATOR,    StringType(),  nullable=False),
    StructField(COL_VALUE,        DoubleType(),  nullable=True),
    StructField(COL_SOURCE,       StringType(),  nullable=False),
])

SOURCE_WDI   = "wdi"
SOURCE_MACRO = "macro"
SOURCE_GMD   = "gmd"
