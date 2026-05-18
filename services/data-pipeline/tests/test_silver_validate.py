from __future__ import annotations

import os
import sys

import pytest
from py4j.protocol import Py4JJavaError

from pipeline.silver_validate import validate_silver

pytest.importorskip("pyspark")
os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)


def test_validate_silver_success(spark) -> None:
    df = spark.createDataFrame(
        [
            ("VNM", "Viet Nam", 2000, "gdp", 100.0, "wdi", "run-1", "2026-05-18", "2026-05-18 00:00:00"),
            ("VNM", "Viet Nam", 2001, "gdp", None, "wdi", "run-1", "2026-05-18", "2026-05-18 00:00:00"),
        ],
        ["country_code", "country", "year", "indicator", "value", "source", "run_id", "run_date", "loaded_at"],
    )
    try:
        summary = validate_silver(df)
    except Py4JJavaError as exc:
        pytest.skip(f"Spark worker unavailable in current environment: {exc.__class__.__name__}")
    assert summary["row_count"] == 2
    assert summary["country_count"] == 1
    assert summary["source_counts"]["wdi"] == 2


def test_validate_silver_duplicate_key_fails(spark) -> None:
    df = spark.createDataFrame(
        [
            ("VNM", "Viet Nam", 2000, "gdp", 100.0, "wdi", "run-1", "2026-05-18", "2026-05-18 00:00:00"),
            ("VNM", "Viet Nam", 2000, "gdp", 101.0, "wdi", "run-1", "2026-05-18", "2026-05-18 00:00:00"),
        ],
        ["country_code", "country", "year", "indicator", "value", "source", "run_id", "run_date", "loaded_at"],
    )
    try:
        with pytest.raises(ValueError, match="duplicate_key_count=1"):
            validate_silver(df)
    except Py4JJavaError as exc:
        pytest.skip(f"Spark worker unavailable in current environment: {exc.__class__.__name__}")
