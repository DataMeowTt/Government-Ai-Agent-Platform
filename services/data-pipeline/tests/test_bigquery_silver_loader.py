from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from warehouse.bigquery_silver_loader import (
    LoadBlockedError,
    execute_silver_load,
    validate_local_input,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
PIPELINE_DIR = REPO_ROOT / "services" / "data-pipeline"


class _Field:
    def __init__(self, name: str) -> None:
        self.name = name


class _Table:
    def __init__(self, rows: int) -> None:
        self.num_rows = rows
        self.schema = [
            _Field("country_code"),
            _Field("country"),
            _Field("year"),
            _Field("indicator"),
            _Field("value"),
            _Field("source"),
            _Field("run_id"),
            _Field("run_date"),
            _Field("loaded_at"),
        ]


class _Job:
    def __init__(self, job_id: str, rows: list[tuple[Any, ...]] | None = None) -> None:
        self.job_id = job_id
        self._rows = rows or []

    def result(self) -> list[tuple[Any, ...]]:
        return self._rows


class _Client:
    def __init__(self, expected_rows: int, source_counts: dict[str, int]) -> None:
        self.expected_rows = expected_rows
        self.source_counts = source_counts
        self.tables: dict[str, _Table] = {}
        self.load_calls: list[str] = []
        self.copy_calls: list[tuple[str, str]] = []
        self.query_calls: list[str] = []

    def get_table(self, table_id: str) -> _Table:
        return self.tables.setdefault(table_id, _Table(0))

    def load_table_from_file(self, file_obj: Any, table_id: str, *, job_config: Any, location: str) -> _Job:
        del file_obj, job_config, location
        self.load_calls.append(table_id)
        self.tables[table_id] = _Table(self.expected_rows)
        return _Job(f"load_{len(self.load_calls)}")

    def copy_table(self, source: str, destination: str, *, job_config: Any, location: str) -> _Job:
        del job_config, location
        self.copy_calls.append((source, destination))
        self.tables[destination] = _Table(self.tables[source].num_rows)
        return _Job("copy_1")

    def query(self, query: str, *, job_config: Any, location: str) -> _Job:
        del job_config, location
        self.query_calls.append(query)
        if "GROUP BY source" in query:
            rows = [(key, value) for key, value in sorted(self.source_counts.items())]
        else:
            rows = [(self.expected_rows,)]
        return _Job(f"query_{len(self.query_calls)}", rows)


def _write_fixture(base_dir: Path, *, source: str = "wdi") -> tuple[Path, Path, dict[str, Any]]:
    run_dir = base_dir / "run"
    silver_dir = run_dir / "silver_indicators"
    silver_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        [
            {
                "country_code": "VNM",
                "country": "Viet Nam",
                "year": 2025,
                "indicator": "gdp",
                "value": 100.0,
                "source": source,
                "run_id": "run",
                "run_date": pd.to_datetime("2026-05-18").date(),
                "loaded_at": pd.Timestamp("2026-05-18T00:00:00Z"),
            }
        ]
    )
    frame.to_parquet(silver_dir / "part-00000.parquet", index=False)
    manifest_path = run_dir / "silver_manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    plan = {
        "bigquery_write_approved": False,
        "cluster": ["country_code", "indicator", "source"],
        "dataset": "gov_ai_silver",
        "dry_run": True,
        "job_started": False,
        "local_manifest_path": str(manifest_path),
        "local_silver_path": str(silver_dir),
        "location": "asia-southeast1",
        "partition": {"type": "integer_range", "column": "year", "start": 1980, "end": 2031, "interval": 1},
        "project_id": "western-pivot-452008-a6",
        "row_count": 1,
        "source_counts": {source: 1},
        "source_format": "parquet",
        "table": "silver_indicators",
        "table_id": "western-pivot-452008-a6.gov_ai_silver.silver_indicators",
    }
    plan_path = base_dir / "load_plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    return silver_dir, plan_path, plan


def test_loader_help() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "jobs.load_silver_bigquery", "--help"],
        cwd=PIPELINE_DIR,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Load validated local Silver indicators into BigQuery" in result.stdout


def test_execute_blocks_without_approval_before_cloud_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _silver_dir, plan_path, plan = _write_fixture(tmp_path)
    monkeypatch.delenv("BIGQUERY_WRITE_APPROVED", raising=False)

    def fail_client(project_id: str, location: str) -> Any:
        raise AssertionError(f"client should not be created: {project_id} {location}")

    with pytest.raises(LoadBlockedError):
        execute_silver_load(
            plan=plan,
            load_plan_path=str(plan_path),
            project_id="western-pivot-452008-a6",
            dataset="gov_ai_silver",
            table="silver_indicators",
            location="asia-southeast1",
            approval_env="BIGQUERY_WRITE_APPROVED",
            output_dir=tmp_path / "out",
            client_factory=fail_client,
            active_project_getter=lambda: "western-pivot-452008-a6",
        )

    preview = (tmp_path / "out" / "load_command_preview.txt").read_text(encoding="utf-8")
    assert "$env:BIGQUERY_WRITE_APPROVED='true'" in preview


def test_validate_local_input_rejects_fao_macro(tmp_path: Path) -> None:
    _silver_dir, _plan_path, plan = _write_fixture(tmp_path, source="fao_macro")

    with pytest.raises(ValueError, match="fao_macro"):
        validate_local_input(plan)


def test_execute_uses_staging_then_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _silver_dir, plan_path, plan = _write_fixture(tmp_path, source="macro")
    monkeypatch.setenv("BIGQUERY_WRITE_APPROVED", "true")
    fake_client = _Client(expected_rows=1, source_counts={"macro": 1})

    payload = execute_silver_load(
        plan=plan,
        load_plan_path=str(plan_path),
        project_id="western-pivot-452008-a6",
        dataset="gov_ai_silver",
        table="silver_indicators",
        location="asia-southeast1",
        approval_env="BIGQUERY_WRITE_APPROVED",
        output_dir=tmp_path / "out",
        staging_table="silver_indicators_staging_run_20260518_000000",
        client_factory=lambda project_id, location: fake_client,
        active_project_getter=lambda: "western-pivot-452008-a6",
    )

    result = payload["result"]
    validation = payload["validation"]
    assert result["staging_table_used"] is True
    assert result["staging_table_id"] == "western-pivot-452008-a6.gov_ai_silver.silver_indicators_staging_run_20260518_000000"
    assert result["target_table_id"] == "western-pivot-452008-a6.gov_ai_silver.silver_indicators"
    assert result["load_job_ids"] == ["load_1"]
    assert result["copy_job_id"] == "copy_1"
    assert result["target_row_count_after"] == 1
    assert validation["bigquery_validation"]["source_counts_match_expected"] is True
    assert (tmp_path / "out" / "load_result.json").exists()
    assert (tmp_path / "out" / "load_validation.json").exists()
    assert fake_client.copy_calls == [
        (
            "western-pivot-452008-a6.gov_ai_silver.silver_indicators_staging_run_20260518_000000",
            "western-pivot-452008-a6.gov_ai_silver.silver_indicators",
        )
    ]
