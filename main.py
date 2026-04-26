from pyspark.sql import SparkSession

from pipeline.job import run
from utils.logger import get_logger

log = get_logger("main")

if __name__ == "__main__":
    log.info("MAIN | spark session starting")
    spark = (
        SparkSession.builder
        .appName("GovernmentAI-Processing")
        .master("spark://spark-master:7077")
        .config("spark.sql.shuffle.partitions", "8")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    log.info("MAIN | spark session ready")

    try:
        run(spark)
    finally:
        spark.stop()
        log.info("MAIN | spark session stopped")
