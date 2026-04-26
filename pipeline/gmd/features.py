from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.window import Window


def compute_gmd_features(df: DataFrame) -> DataFrame:
    w     = Window.partitionBy("country_code").orderBy("year")
    w_5yr = Window.partitionBy("country_code").orderBy("year").rowsBetween(-4, 0)

    return (
        df
        .withColumn("rgdp_growth_yoy",
            (F.col("rgdp") - F.lag("rgdp").over(w)) / F.lag("rgdp").over(w) * 100)

        .withColumn("rolling_mean_5yr",
            F.avg("rgdp_growth_yoy").over(w_5yr))

        .withColumn("log_rgdp_pc_usd",
            F.log(F.col("rgdp_pc_usd") + F.lit(1)))

        .withColumn("development_group",
            F.when(F.col("rgdp_pc_usd") < 1000,  F.lit(0.0))
            .when(F.col("rgdp_pc_usd") < 5000,   F.lit(1.0))
            .when(F.col("rgdp_pc_usd") < 15000,  F.lit(2.0))
            .otherwise(F.lit(3.0)))

        .withColumn("trade_balance_gdp",
            F.col("exports_gdp") - F.col("imports_gdp"))

        .withColumn("hcons_growth",
            (F.col("hcons_usd") - F.lag("hcons_usd").over(w)) / F.lag("hcons_usd").over(w) * 100)

        .withColumn("fiscal_balance_gdp",
            F.col("govrev_gdp") - F.col("govexp_gdp"))

        .withColumn("cumulative_deficit_5yr",
            F.sum("fiscal_balance_gdp").over(w_5yr))

        .withColumn("debt_change_yoy",
            F.col("govdebt_gdp") - F.lag("govdebt_gdp").over(w))

        .withColumn("real_interest_rate",
            F.col("ltrate") - F.col("infl"))

        .withColumn("crisis_composite",
            F.col("sov_debt_crisis") + F.col("currency_crisis") + F.col("banking_crisis"))

        .withColumn("crisis_any",
            F.when(F.col("crisis_composite") >= 1, F.lit(1.0)).otherwise(F.lit(0.0)))

        .withColumn("reer_ma5", F.avg("reer").over(w_5yr))
        .withColumn("reer_deviation",
            (F.col("reer") - F.col("reer_ma5")) / F.col("reer_ma5") * 100)
        .drop("reer_ma5")

        .withColumn("spending_efficiency",
            F.col("rgdp_growth_yoy") / F.col("govexp_gdp"))

        .withColumn("income_group_encoded",
            F.when(F.col("income_group") == "Low income",          F.lit(0.0))
            .when(F.col("income_group") == "Lower middle income",   F.lit(1.0))
            .when(F.col("income_group") == "Upper middle income",   F.lit(2.0))
            .when(F.col("income_group") == "High income",           F.lit(3.0))
            .otherwise(F.lit(None).cast("double")))
    )
