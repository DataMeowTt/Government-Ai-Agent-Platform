from __future__ import annotations

import json
import os
import subprocess
import sys
import shutil
from pathlib import Path

import pandas as pd
import pytest

from warehouse.bigquery_silver_load_plan import (
    TARGET_DATASET,
    TARGET_LOCATION,
    TARGET_PROJECT_ID,
    TARGET_TABLE,
    build_silver_load_plan,
    resolve_silver_artifacts,
    write_load_plan_artifacts,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
PIPELINE_DIR = REPO_ROOT / "services" / "data-pipeline"
CONTRACT_PATH = REPO_ROOT / "contracts" / "table_contract.yaml"


def _run_plan(args: list[str]) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    return subprocess.run(
        [sys.executable, "-m", "jobs.plan_silver_bigquery_load", *args],
        cwd=PIPELINE_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _write_manifest(
    run_dir: Path,
    *,
    output_format: str,
    run_id: str,
    run_date: str,
    silver_output_path: Path,
    row_count: int,
    country_count: int,
    indicator_count: int,
    source_counts: dict[str, int],
    duplicate_key_count: int = 0,
) -> Path:
    manifest_path = run_dir / "silver_manifest.json"
    manifest = {
        "generated_at": "2026-05-18T00:00:00+00:00",
        "input_paths": {"dummy": "dummy"},
        "manifest_path": str(manifest_path),
        "output_format": output_format,
        "run_date": run_date,
        "run_id": run_id,
        "silver_output_path": str(silver_output_path),
        "source": "all",
        "spark_master": "local[*]",
        "validation_summary": {
            "country_count": country_count,
            "duplicate_key_count": duplicate_key_count,
            "indicator_count": indicator_count,
            "null_value_rate": 0.0,
            "row_count": row_count,
            "source_counts": source_counts,
            "year_max": 2026,
            "year_min": 2025,
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def _write_contract(repo_root: Path) -> Path:
    contract_dir = repo_root / "contracts"
    contract_dir.mkdir(parents=True, exist_ok=True)
    target = contract_dir / "table_contract.yaml"
    shutil.copyfile(CONTRACT_PATH, target)
    return target


def _build_parquet_fixture(base_dir: Path) -> tuple[Path, Path]:
    run_dir = base_dir / "silver_local_output"
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
                "source": "wdi",
                "run_id": "local-silver-smoke",
                "run_date": "2026-05-18",
                "loaded_at": "2026-05-18T00:00:00+00:00",
            },
            {
                "country_code": "VNM",
                "country": "Viet Nam",
                "year": 2026,
                "indicator": "infl",
                "value": 7.5,
                "source": "macro",
                "run_id": "local-silver-smoke",
                "run_date": "2026-05-18",
                "loaded_at": "2026-05-18T00:00:00+00:00",
            },
        ]
    )
    frame.to_parquet(silver_dir / "part-00000.parquet", index=False)
    manifest_path = _write_manifest(
        run_dir,
        output_format="parquet",
        run_id="local-silver-smoke",
        run_date="2026-05-18",
        silver_output_path=silver_dir,
        row_count=2,
        country_count=1,
        indicator_count=2,
        source_counts={"wdi": 1, "macro": 1},
    )
    return silver_dir, manifest_path


def _build_csv_fixture(base_dir: Path) -> tuple[Path, Path]:
    run_dir = base_dir / "silver_fixture_output"
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
                "source": "wdi",
                "run_id": "silver-fixture",
                "run_date": "2026-05-18",
                "loaded_at": "2026-05-18T00:00:00+00:00",
            },
            {
                "country_code": "VNM",
                "country": "Viet Nam",
                "year": 2026,
                "indicator": "infl",
                "value": 7.5,
                "source": "gmd",
                "run_id": "silver-fixture",
                "run_date": "2026-05-18",
                "loaded_at": "2026-05-18T00:00:00+00:00",
            },
        ]
    )
    frame.to_csv(silver_dir / "part-00000.csv", index=False)
    manifest_path = _write_manifest(
        run_dir,
        output_format="csv",
        run_id="silver-fixture",
        run_date="2026-05-18",
        silver_output_path=silver_dir,
        row_count=2,
        country_count=1,
        indicator_count=2,
        source_counts={"wdi": 1, "gmd": 1},
    )
    return silver_dir, manifest_path


def test_plan_help() -> None:
    result = _run_plan(["--help"])
    assert result.returncode == 0
    assert "dry-run BigQuery load" in result.stdout


def test_resolve_artifacts_auto_detect(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    silver_dir, manifest_path = _build_parquet_fixture(repo_root / "tmp")

    artifacts = resolve_silver_artifacts(repo_root=repo_root)

    assert artifacts.local_silver_path == silver_dir.resolve()
    assert artifacts.local_manifest_path == manifest_path.resolve()
    assert artifacts.source_format == "parquet"
    assert artifacts.manifest["run_id"] == "local-silver-smoke"


def test_build_plan_from_parquet_fixture(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _write_contract(repo_root)
    silver_dir, manifest_path = _build_parquet_fixture(repo_root / "tmp")
    output_dir = tmp_path / "plan"

    plan = build_silver_load_plan(
        repo_root=repo_root,
        output_dir=output_dir,
    )
    artifacts = write_load_plan_artifacts(plan, output_dir)

    assert plan["project_id"] == TARGET_PROJECT_ID
    assert plan["dataset"] == TARGET_DATASET
    assert plan["table"] == TARGET_TABLE
    assert plan["location"] == TARGET_LOCATION
    assert plan["table_id"] == "western-pivot-452008-a6.gov_ai_silver.silver_indicators"
    assert plan["local_silver_path"] == str(silver_dir.resolve())
    assert plan["local_manifest_path"] == str(manifest_path.resolve())
    assert plan["source_format"] == "parquet"
    assert plan["row_count"] == 2
    assert plan["country_count"] == 1
    assert plan["indicator_count"] == 2
    assert plan["source_counts"] == {"macro": 1, "wdi": 1}
    assert plan["duplicate_key_count"] == 0
    assert plan["dry_run"] is True
    assert plan["bigquery_write_approved"] is False
    assert plan["job_started"] is False
    assert plan["schema_validation_summary"]["matches_contract"] is True
    assert plan["schema_validation_summary"]["manifest_path_matches_input"] is True
    assert artifacts["load_plan"].exists()
    assert artifacts["summary"].exists()
    saved = json.loads(artifacts["load_plan"].read_text(encoding="utf-8"))
    assert saved["dry_run"] is True
    assert saved["bigquery_write_approved"] is False
    assert saved["job_started"] is False


def test_build_plan_from_csv_fixture(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _write_contract(repo_root)
    silver_dir, manifest_path = _build_csv_fixture(repo_root / "tmp")

    plan = build_silver_load_plan(
        silver_output_dir=str(silver_dir),
        silver_manifest=str(manifest_path),
        repo_root=repo_root,
    )

    assert plan["source_format"] == "csv"
    assert plan["row_count"] == 2
    assert plan["source_counts"] == {"gmd": 1, "wdi": 1}
    assert plan["schema_validation_summary"]["matches_contract"] is True
    assert plan["schema_validation_summary"]["source_counts_match_manifest"] is True


def test_missing_artifacts_reports_checked_paths(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    with pytest.raises(FileNotFoundError) as excinfo:
        resolve_silver_artifacts(repo_root=repo_root)

    message = str(excinfo.value)
    assert "No local Silver output/manifest could be auto-detected." in message
    assert "silver_local_output" in message
    assert "python -m jobs.build_silver" in message


def test_cli_writes_plan_files(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    silver_dir, manifest_path = _build_parquet_fixture(repo_root / "tmp")
    output_dir = tmp_path / "runtime"

    result = _run_plan(
        [
            "--silver-output-dir",
            str(silver_dir),
            "--silver-manifest",
            str(manifest_path),
            "--project-id",
            TARGET_PROJECT_ID,
            "--dataset",
            TARGET_DATASET,
            "--table",
            TARGET_TABLE,
            "--location",
            TARGET_LOCATION,
            "--output-dir",
            str(output_dir),
        ]
    )

    assert result.returncode == 0, result.stderr
    plan_path = output_dir / "load_plan.json"
    summary_path = output_dir / "load_plan_summary.txt"
    assert plan_path.exists()
    assert summary_path.exists()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan["dry_run"] is True
    assert plan["bigquery_write_approved"] is False
    assert plan["job_started"] is False
