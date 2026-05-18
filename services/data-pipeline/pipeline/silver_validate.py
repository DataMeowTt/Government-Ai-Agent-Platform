from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyspark.sql import DataFrame

REQUIRED_COLUMNS = [
    "country_code",
    "country",
    "year",
    "indicator",
    "value",
    "source",
    "run_id",
    "run_date",
    "loaded_at",
]
ALLOWED_SOURCES = {"wdi", "gmd", "macro", "fao_macro"}


def validate_silver(df: "DataFrame") -> dict:
    from pyspark.sql import functions as F

    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    row_count = df.count()
    if row_count <= 0:
        raise ValueError("Validation failed: row_count must be > 0.")

    invalid_country_code = df.filter(
        F.col("country_code").isNotNull() & (~F.col("country_code").rlike(r"^[A-Z]{3}$"))
    ).count()
    invalid_year = df.filter(~F.col("year").between(1980, 2030)).count()
    invalid_source = df.filter(~F.col("source").isin(list(ALLOWED_SOURCES))).count()
    null_metadata = df.filter(
        F.col("run_id").isNull() | F.col("run_date").isNull() | F.col("loaded_at").isNull()
    ).count()
    invalid_numeric = df.filter(
        F.col("value").isNotNull() & F.col("value").cast("double").isNull()
    ).count()

    duplicate_key_count = (
        df.groupBy("country_code", "year", "indicator", "source")
        .count()
        .filter(F.col("count") > 1)
        .select(F.sum(F.col("count") - F.lit(1)).alias("duplicate_rows"))
        .first()["duplicate_rows"]
    )
    duplicate_key_count = int(duplicate_key_count or 0)

    if any(
        count > 0
        for count in (
            invalid_country_code,
            invalid_year,
            invalid_source,
            null_metadata,
            invalid_numeric,
            duplicate_key_count,
        )
    ):
        raise ValueError(
            "Validation failed: "
            f"invalid_country_code={invalid_country_code}, "
            f"invalid_year={invalid_year}, "
            f"invalid_source={invalid_source}, "
            f"null_metadata={null_metadata}, "
            f"invalid_numeric={invalid_numeric}, "
            f"duplicate_key_count={duplicate_key_count}"
        )

    stats = df.agg(
        F.countDistinct("country_code").alias("country_count"),
        F.countDistinct("indicator").alias("indicator_count"),
        F.min("year").alias("year_min"),
        F.max("year").alias("year_max"),
        F.sum(F.when(F.col("value").isNull(), F.lit(1)).otherwise(F.lit(0))).alias("null_value_count"),
    ).first()
    source_counts = {
        row["source"]: int(row["count"])
        for row in df.groupBy("source").count().collect()
    }

    return {
        "row_count": int(row_count),
        "country_count": int(stats["country_count"]),
        "indicator_count": int(stats["indicator_count"]),
        "year_min": int(stats["year_min"]),
        "year_max": int(stats["year_max"]),
        "source_counts": source_counts,
        "duplicate_key_count": duplicate_key_count,
        "null_value_rate": float(stats["null_value_count"] / row_count),
    }
