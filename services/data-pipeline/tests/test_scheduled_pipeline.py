from __future__ import annotations

import json
from pathlib import Path

from jobs import scheduled_pipeline


def _manifest(fingerprint: str, status: str = "valid") -> dict:
    return {
        "run_id": "run-1",
        "run_date": "2026-05-24",
        "status": status,
        "sources": [
            {
                "source_name": "wdi",
                "combined_fingerprint": fingerprint,
            }
        ],
    }


def _write_baseline(path: Path, fingerprint: str) -> None:
    path.write_text(json.dumps(_manifest(fingerprint)), encoding="utf-8")


def _run(tmp_path: Path, args: list[str]) -> tuple[dict, dict]:
    runtime_dir = tmp_path / "runtime"
    out_dir = tmp_path / "out"
    code = scheduled_pipeline.main(
        [
            *args,
            "--runtime-dir",
            str(runtime_dir),
            "--output-dir",
            str(out_dir),
        ]
    )
    plan = json.loads((out_dir / "scheduled_pipeline_plan.json").read_text(encoding="utf-8"))
    metadata = json.loads((out_dir / "pipeline_run_metadata.json").read_text(encoding="utf-8"))
    assert code in {0, 1}
    return plan, metadata


def test_unchanged_candidate_skips_publish_and_success_update(tmp_path: Path, monkeypatch) -> None:
    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline, "same")
    monkeypatch.setattr(scheduled_pipeline, "run_acquisition", lambda **_: (_manifest("same"), []))
    plan, metadata = _run(
        tmp_path,
        ["--mode", "dry_run", "--run-id", "run-1", "--run-date", "2026-05-24", "--previous-success-manifest", str(baseline)],
    )
    assert metadata["status"] == "SKIPPED_UNCHANGED"
    assert metadata["source_changed"] is False
    assert metadata["publish_performed"] is False
    assert metadata["last_successful_updated"] is False
    assert metadata["latest_data_year"] is None
    assert metadata["sources_json"] is None
    assert metadata["cloud_write"] is False
    assert metadata["warehouse_publish_performed"] is False
    assert plan["planned_actions"] == []
    assert plan["publish_performed"] is False


def test_changed_candidate_has_ordered_actions_but_not_executed(tmp_path: Path, monkeypatch) -> None:
    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline, "old")
    monkeypatch.setattr(scheduled_pipeline, "run_acquisition", lambda **_: (_manifest("new"), []))
    plan, metadata = _run(
        tmp_path,
        ["--mode", "dry_run", "--run-id", "run-1", "--run-date", "2026-05-24", "--previous-success-manifest", str(baseline)],
    )
    assert metadata["status"] == "DRY_RUN_CHANGED"
    assert metadata["source_changed"] is True
    assert metadata["warehouse_publish_planned"] is True
    assert metadata["warehouse_publish_performed"] is False
    assert metadata["latest_data_year"] is None
    assert metadata["sources_json"] is None
    assert metadata["cloud_write"] is False
    assert metadata["publish_performed"] is False
    assert [item["action"] for item in plan["planned_actions"]] == scheduled_pipeline.PLANNED_ACTIONS
    assert all(item["executed"] is False for item in plan["planned_actions"])
    assert all(item["cloud_write"] is False for item in plan["planned_actions"])
    assert plan["publish_performed"] is False


def test_failed_acquisition_is_failed_and_no_last_success_update(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(scheduled_pipeline, "run_acquisition", lambda **_: (_manifest("x", status="acquisition_failed"), [{"error": "x"}]))
    _plan, metadata = _run(
        tmp_path,
        ["--mode", "dry_run", "--run-id", "run-1", "--run-date", "2026-05-24"],
    )
    assert metadata["status"] == "FAILED"
    assert metadata["publish_performed"] is False
    assert metadata["last_successful_updated"] is False
    assert metadata["cloud_write"] is False
    assert metadata["latest_data_year"] is None
    assert metadata["sources_json"] is None


def test_baseline_path_is_last_successful_manifest_input(tmp_path: Path, monkeypatch) -> None:
    baseline = tmp_path / "last_successful_manifest.json"
    _write_baseline(baseline, "old")
    monkeypatch.setattr(scheduled_pipeline, "run_acquisition", lambda **_: (_manifest("new"), []))
    plan, metadata = _run(
        tmp_path,
        ["--mode", "dry_run", "--run-id", "run-1", "--run-date", "2026-05-24", "--previous-success-manifest", str(baseline)],
    )
    assert plan["baseline_manifest_path"] == str(baseline)
    assert metadata["baseline_success_manifest_path"] == str(baseline)


def test_force_behavior_recorded_without_faking_source_changed(tmp_path: Path, monkeypatch) -> None:
    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline, "same")
    monkeypatch.setattr(scheduled_pipeline, "run_acquisition", lambda **_: (_manifest("same"), []))
    _plan, metadata = _run(
        tmp_path,
        [
            "--mode",
            "dry_run",
            "--run-id",
            "run-1",
            "--run-date",
            "2026-05-24",
            "--previous-success-manifest",
            str(baseline),
            "--force",
        ],
    )
    assert metadata["status"] == "DRY_RUN_CHANGED"
    assert metadata["source_changed"] is False
    assert metadata["force_requested"] is True
    assert metadata["force_applied"] is True
