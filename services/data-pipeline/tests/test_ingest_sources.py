from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PIPELINE_DIR = REPO_ROOT / "services" / "data-pipeline"


def _run_ingest(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "jobs.ingest_sources", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_ingest_sources_help() -> None:
    result = _run_ingest(["--help"], PIPELINE_DIR)
    assert result.returncode == 0
    assert "Ingest configured sources" in result.stdout


def test_ingest_sources_dry_run_all_reports_missing_inputs(tmp_path: Path) -> None:
    output_dir = tmp_path / "dry_run_all"
    result = _run_ingest(
        [
            "--dry-run",
            "--source",
            "all",
            "--output-dir",
            str(output_dir),
        ],
        PIPELINE_DIR,
    )

    assert result.returncode == 0, result.stderr
    source_manifest = json.loads((output_dir / "source_manifest.json").read_text(encoding="utf-8"))
    pipeline_manifest = json.loads((output_dir / "pipeline_manifest.json").read_text(encoding="utf-8"))

    assert source_manifest["source_count"] == 3
    assert source_manifest["missing_count"] == 3
    assert source_manifest["ingested_count"] == 0
    assert len(source_manifest["sources"]) == 3
    assert pipeline_manifest["source_count"] == 3
    assert source_manifest["status"] == "missing_inputs"
    assert result.stdout.strip()


def test_ingest_sources_smoke_fixture_creates_local_bronze_snapshot(tmp_path: Path) -> None:
    output_dir = tmp_path / "smoke"
    result = _run_ingest(
        [
            "--dry-run",
            "--source",
            "gmd",
            "--smoke-fixture",
            "--output-dir",
            str(output_dir),
        ],
        PIPELINE_DIR,
    )

    assert result.returncode == 0, result.stderr
    source_manifest = json.loads((output_dir / "source_manifest.json").read_text(encoding="utf-8"))
    bronze_dir = output_dir / "bronze" / "gmd" / f"run_date={source_manifest['run_date']}"
    payload_path = bronze_dir / "payload.csv"
    metadata_path = bronze_dir / "bronze_snapshot.json"

    assert source_manifest["source_count"] == 1
    assert source_manifest["ingested_count"] == 1
    assert source_manifest["sources"][0]["is_test_fixture"] is True
    assert source_manifest["sources"][0]["status"] == "ingested"
    assert payload_path.exists()
    assert metadata_path.exists()
    assert "test_fixture" in payload_path.read_text(encoding="utf-8")
