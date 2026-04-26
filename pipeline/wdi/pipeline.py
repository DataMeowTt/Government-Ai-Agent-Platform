from pyspark.sql import DataFrame, SparkSession

from pipeline.wdi.filter import filter_by_country, filter_by_indicator, validate_all
from pipeline.wdi.transform import flatten_years, map_indicator_codes, unpivot_all
from pipeline.wdi.features import compute_wdi_features
from utils.logger import get_logger

log = get_logger("pipeline.wdi")


def process_wdi(spark: SparkSession, path: str) -> DataFrame:
    try:
        log.info("WDI | start | path=%s", path)

        raw      = spark.read.csv(path, header=True, inferSchema=False)
        log.info("WDI | loaded | rows=%d", raw.count())

        filtered = filter_by_country(raw)
        filtered = filter_by_indicator(filtered)
        log.info("WDI | filtered | rows=%d", filtered.count())

        normalized = flatten_years(filtered)
        mapped     = map_indicator_codes(normalized)

        featured  = compute_wdi_features(mapped)
        log.info("WDI | features computed")

        validated = validate_all(featured)
        log.info("WDI | validated | rows=%d", validated.count())

        result = unpivot_all(validated)
        log.info("WDI | done | output_rows=%d", result.count())
        return result

    except Exception as e:
        log.error("WDI | failed | error=%s", e, exc_info=True)
        raise
