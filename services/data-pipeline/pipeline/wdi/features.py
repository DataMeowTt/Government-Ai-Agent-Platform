from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.window import Window


def compute_wdi_features(long: DataFrame) -> DataFrame:
    wide = (
        long.groupBy("country_code", "country", "year", "source")
        .pivot("indicator")
        .agg(F.first("value"))
    )

    w_order = Window.partitionBy("country_code").orderBy("year")
    w_3yr   = Window.partitionBy("country_code").orderBy("year").rowsBetween(-2, 0)
    w_5yr   = Window.partitionBy("country_code").orderBy("year").rowsBetween(-4, 0)

    return (
        wide
        .withColumn("youth_unemployment_gap",
            F.col("unemployment_total") - F.col("unemployment_youth"))

        .withColumn("youth_gap_ratio",
            F.col("unemployment_youth") / F.col("unemployment_total"))

        .withColumn("log_pop_density",
            F.log(F.col("population_density") + F.lit(1)))

        .withColumn("inflation_gap",
            F.col("inflation_consumer_prices") - F.col("inflation_gdp_deflator"))

        .withColumn("rolling_3yr_avg_cpi",
            F.avg("inflation_consumer_prices").over(w_3yr))

        .withColumn("poverty_change_5yr",
            F.col("poverty_headcount_ratio") - F.lag("poverty_headcount_ratio", 5).over(w_order))

        .withColumn("gdp_pc_growth_gap",
            F.col("gdp_growth") - F.col("gdp_per_capita_growth"))

        .withColumn("_gdp_count", F.count("gdp_growth").over(w_5yr))
        .withColumn("gdp_growth_trend_5yr",
            F.when(F.col("_gdp_count") >= 3, F.avg("gdp_growth").over(w_5yr))
            .otherwise(F.lit(None)))
        .drop("_gdp_count")

        .withColumn("trend_deviation",
            F.col("gdp_growth") - F.col("gdp_growth_trend_5yr"))
    )
