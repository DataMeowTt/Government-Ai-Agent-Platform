from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from sources.gcs_upload import build_gcs_uri, build_upload_plan, execute_upload_plan


REPO_ROOT = Path(__file__).resolve().parents[3]
PIPELINE_DIR = REPO_ROOT / "services" / "data-pipeline"
UPLOAD_PLAN_PATH = REPO_ROOT / "tmp" / "gcs_upload_runtime" / "upload_plan.json"


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _build_local_bronze_fixture(tmp_path: Path) -> Path:
    output_dir = tmp_path / "local_bronze"
    for source_name, file_name in [
        ("wdi", "WDICSV.csv"),
        ("gmd", "GMD.csv"),
        ("fao_macro", "Macro-Statistics_Key_Indicators_E_All_Data_(Normalized).csv"),
    ]:
        bronze_root = output_dir / "bronze" / source_name / "run_date=2026-05-18"
        _write_text(bronze_root / "bronze_snapshot.json", "{}\n")
        _write_text(bronze_root / "files" / file_name, "a,b\n1,2\n")
    _write_text(output_dir / "source_manifest.json", "{}\n")
    _write_text(output_dir / "pipeline_manifest.json", "{}\n")
    _write_text(output_dir / "ops_records.json", "{}\n")
    return output_dir


def _run_ingest(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "jobs.ingest_sources", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_build_gcs_uri_uses_forward_slashes() -> None:
    uri = build_gcs_uri(
        "western-pivot-452008-a6-gov-ai-economic-data",
        "bronze",
        "wdi",
        "run_date=2026-05-18",
        "files",
        "WDICSV.csv",
    )

    assert uri == (
        "gs://western-pivot-452008-a6-gov-ai-economic-data/"
        "bronze/wdi/run_date=2026-05-18/files/WDICSV.csv"
    )
    assert "\\" not in uri


def test_upload_plan_contains_expected_bronze_and_manifest_targets(tmp_path: Path) -> None:
    output_dir = _build_local_bronze_fixture(tmp_path)

    plan = build_upload_plan(
        output_dir=output_dir,
        bucket="western-pivot-452008-a6-gov-ai-economic-data",
        run_id="gcs-upload-plan",
        run_date="2026-05-18",
        dry_run=True,
        cloud_approved=False,
    )

    assert plan["mode"] == "dry_run"
    assert plan["object_count"] == 9
    assert plan["total_bytes"] > 0
    assert plan["source_names"] == ["fao_macro", "gmd", "wdi"]
    assert any("/bronze/wdi/run_date=2026-05-18/" in item["target_gcs_uri"] for item in plan["objects"])
    assert any("/bronze/gmd/run_date=2026-05-18/" in item["target_gcs_uri"] for item in plan["objects"])
    assert any("/bronze/fao_macro/run_date=2026-05-18/" in item["target_gcs_uri"] for item in plan["objects"])
    assert any(
        item["target_gcs_uri"]
        == "gs://western-pivot-452008-a6-gov-ai-economic-data/manifests/source_manifest/run_date=2026-05-18/source_manifest.json"
        for item in plan["objects"]
    )
    assert any(
        item["target_gcs_uri"]
        == "gs://western-pivot-452008-a6-gov-ai-economic-data/manifests/pipeline_manifest/run_date=2026-05-18/pipeline_manifest.json"
        for item in plan["objects"]
    )
    assert any(
        item["target_gcs_uri"]
        == "gs://western-pivot-452008-a6-gov-ai-economic-data/manifests/ops_records/run_date=2026-05-18/ops_records.json"
        for item in plan["objects"]
    )


def test_cloud_write_approved_false_blocks_execution(tmp_path: Path, monkeypatch) -> None:
    output_dir = _build_local_bronze_fixture(tmp_path)
    monkeypatch.setenv("CLOUD_WRITE_APPROVED", "false")

    plan = build_upload_plan(
        output_dir=output_dir,
        bucket="western-pivot-452008-a6-gov-ai-economic-data",
        run_id="gcs-upload-plan",
        run_date="2026-05-18",
        dry_run=False,
    )
    result = execute_upload_plan(plan)

    assert plan["mode"] == "dry_run"
    assert result["status"] == "blocked"
    assert result["reason"] == "cloud_write_approved_false"


def test_ingest_sources_dry_run_generates_upload_plan_json(tmp_path: Path) -> None:
    output_dir = tmp_path / "local_bronze"
    result = _run_ingest(
        [
            "--source",
            "all",
            "--run-id",
            "gcs-upload-plan",
            "--run-date",
            "2026-05-18",
            "--output-dir",
            str(output_dir),
            "--dry-run",
            "--force",
            "--upload-gcs",
            "--gcs-bucket",
            "western-pivot-452008-a6-gov-ai-economic-data",
        ],
        PIPELINE_DIR,
    )

    assert result.returncode == 0, result.stderr
    assert UPLOAD_PLAN_PATH.exists()

    plan = json.loads(UPLOAD_PLAN_PATH.read_text(encoding="utf-8"))
    assert plan["object_count"] > 0
    assert plan["total_bytes"] > 0
    assert set(plan["source_names"]) == {"wdi", "gmd", "fao_macro"}
    assert all(
        item["target_gcs_uri"].startswith("gs://western-pivot-452008-a6-gov-ai-economic-data/")
        for item in plan["objects"]
    )
    assert any("/bronze/wdi/run_date=2026-05-18/" in item["target_gcs_uri"] for item in plan["objects"])
    assert any("/bronze/gmd/run_date=2026-05-18/" in item["target_gcs_uri"] for item in plan["objects"])
    assert any("/bronze/fao_macro/run_date=2026-05-18/" in item["target_gcs_uri"] for item in plan["objects"])
    assert any(
        "/manifests/source_manifest/run_date=2026-05-18/source_manifest.json" in item["target_gcs_uri"]
        for item in plan["objects"]
    )
    assert any(
        "/manifests/pipeline_manifest/run_date=2026-05-18/pipeline_manifest.json" in item["target_gcs_uri"]
        for item in plan["objects"]
    )
