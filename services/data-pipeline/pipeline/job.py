from datetime import datetime, timezone

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from config.settings import settings
from pipeline.gmd.pipeline import process_gmd
from pipeline.macro.pipeline import process_macro
from pipeline.silver_paths import resolve_silver_inputs
from pipeline.wdi.pipeline import process_wdi
from utils.io_paths import build_silver_output_uris
from utils.logger import get_logger

log = get_logger("pipeline.job")


def _loaded_at_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def add_metadata(df: DataFrame, *, run_id: str, run_date: str, loaded_at: str) -> DataFrame:
    return (
        df
        .withColumn("run_id", F.lit(run_id))
        .withColumn("run_date", F.lit(run_date).cast("date"))
        .withColumn("loaded_at", F.lit(loaded_at).cast("timestamp"))
    )


def save_output(df: DataFrame, path: str, output_format: str) -> None:
    if output_format == "csv":
        df.coalesce(1).write.mode("overwrite").option("header", True).csv(path)
    elif output_format == "parquet":
        df.write.mode("overwrite").parquet(path)
    else:
        raise ValueError(f"Unsupported output format: {output_format!r}")

    log.info("JOB | saved | format=%s | path=%s", output_format, path)


def build_source_frames(
    spark: SparkSession,
    *,
    wdi_path: str | None,
    gmd_path: str | None,
    macro_path: str | None,
    run_id: str,
    run_date: str,
    loaded_at: str | None = None,
) -> dict[str, DataFrame]:
    loaded_at_value = loaded_at or _loaded_at_utc()
    frames: dict[str, DataFrame] = {}
    if wdi_path:
        frames["wdi"] = add_metadata(
            process_wdi(spark, wdi_path),
            run_id=run_id,
            run_date=run_date,
            loaded_at=loaded_at_value,
        )
    if macro_path:
        frames["macro"] = add_metadata(
            process_macro(spark, macro_path),
            run_id=run_id,
            run_date=run_date,
            loaded_at=loaded_at_value,
        )
    if gmd_path:
        frames["gmd"] = add_metadata(
            process_gmd(spark, gmd_path),
            run_id=run_id,
            run_date=run_date,
            loaded_at=loaded_at_value,
        )
    return frames


def union_source_frames(frames: dict[str, DataFrame]) -> DataFrame:
    ordered = [frames[key] for key in ("wdi", "macro", "gmd") if key in frames]
    if not ordered:
        raise ValueError("No source DataFrame available to union.")
    union_df = ordered[0]
    for frame in ordered[1:]:
        union_df = union_df.unionByName(frame)
    return union_df.orderBy("country", "year")


def run(spark: SparkSession) -> None:
    output_format = settings.output_format
    output_uris = build_silver_output_uris(settings.silver_output_uri)

    log.info("JOB | ===== pipeline start =====")
    log.info(
        "JOB | output configured | format=%s | silver_output_uri=%s | run_id=%s | run_date=%s",
        output_format,
        settings.silver_output_uri,
        settings.run_id,
        settings.run_date,
    )

    try:
        input_paths = resolve_silver_inputs(registry_path=settings.source_registry_path)
        frames = build_source_frames(
            spark,
            wdi_path=input_paths["wdi"],
            gmd_path=input_paths["gmd"],
            macro_path=input_paths["fao_macro"],
            run_id=settings.run_id,
            run_date=settings.run_date,
        )

        for key in ("wdi", "macro", "gmd"):
            if key in frames:
                save_output(frames[key], output_uris[key], output_format)

        log.info("JOB | building union")
        union = union_source_frames(frames)
        save_output(union, output_uris["union"], output_format)

        log.info("JOB | ===== pipeline done =====")

    except Exception as e:
        log.error("JOB | pipeline failed | error=%s", e, exc_info=True)
        raise
