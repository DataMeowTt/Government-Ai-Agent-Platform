from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.window import Window


def compute_macro_features(df: DataFrame) -> DataFrame:
    w = Window.partitionBy("country_code").orderBy("year")

    return (
        df
        .withColumn("decade",
            (F.floor(F.col("year") / 10) * 10).cast("double"))

        .withColumn("gfcf_to_gdp",
            F.col("gfcf_value") / F.col("gdp_value") * 100)

        .withColumn("gni_to_gdp",
            F.col("gni_value") / F.col("gdp_value"))

        .withColumn("agri_va_share",
            F.col("agri_va") / F.col("gdp_value") * 100)

        .withColumn("manuf_va_share",
            F.col("manuf_va") / F.col("gdp_value") * 100)

        .withColumn("food_bev_share_manuf",
            F.col("va_foodbev") / F.col("manuf_va") * 100)

        .withColumn("gdp_growth_yoy",
            (F.col("gdp_value") - F.lag("gdp_value").over(w))
            / F.lag("gdp_value").over(w) * 100)
    )
