from pyspark.sql import DataFrame, SparkSession

from pipeline.macro.filter import filter_by_area, filter_by_year, filter_by_item, validate_all
from pipeline.macro.transform import pivot_to_wide, unpivot_all
from pipeline.macro.features import compute_macro_features
from utils.logger import get_logger

log = get_logger("pipeline.macro")


def process_macro(spark: SparkSession, path: str) -> DataFrame:
    try:
        log.info("MACRO | start | path=%s", path)

        raw      = spark.read.csv(path, header=True, inferSchema=False)
        log.info("MACRO | loaded | rows=%d", raw.count())

        filtered = filter_by_area(raw)
        filtered = filter_by_year(filtered)
        filtered = filter_by_item(filtered)
        log.info("MACRO | filtered | rows=%d", filtered.count())

        wide     = pivot_to_wide(filtered)
        log.info("MACRO | pivoted to wide")

        featured  = compute_macro_features(wide)
        log.info("MACRO | features computed")

        validated = validate_all(featured)
        log.info("MACRO | validated | rows=%d", validated.count())

        result = unpivot_all(validated)
        log.info("MACRO | done | output_rows=%d", result.count())
        return result

    except Exception as e:
        log.error("MACRO | failed | error=%s", e, exc_info=True)
        raise
