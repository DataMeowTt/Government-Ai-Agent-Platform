from __future__ import annotations

import json
from pathlib import Path

from ops.source_fingerprint import decide_source_change


def _candidate(status: str = "valid", fingerprint: str = "abc") -> dict:
    return {
        "run_id": "r1",
        "run_date": "2026-05-24",
        "status": status,
        "sources": [
            {
                "source_name": "wdi",
                "combined_fingerprint": fingerprint,
            }
        ],
    }


def test_plan_mode_decision_exact() -> None:
    decision = decide_source_change(mode="plan", candidate_manifest=_candidate(), baseline_path=None)
    assert decision == {
        "run_id": "r1",
        "run_date": "2026-05-24",
        "candidate_status": "PLANNED",
        "baseline_kind": "local_last_successful_manifest_input",
        "baseline_path": None,
        "source_changed": None,
        "changed_sources": [],
        "reason": "plan_only_no_acquisition",
        "should_build_downstream": False,
    }


def test_no_baseline_valid_candidate_is_changed() -> None:
    decision = decide_source_change(mode="dry_run", candidate_manifest=_candidate(), baseline_path=None)
    assert decision["candidate_status"] == "CHANGED_CANDIDATE"
    assert decision["source_changed"] is True
    assert decision["reason"] == "no_last_successful_baseline"
    assert decision["should_build_downstream"] is False


def test_identical_baseline_is_skipped(tmp_path: Path) -> None:
    baseline = _candidate()
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    decision = decide_source_change(mode="dry_run", candidate_manifest=_candidate(), baseline_path=str(baseline_path))
    assert decision["candidate_status"] == "SKIPPED_UNCHANGED"
    assert decision["source_changed"] is False
    assert decision["changed_sources"] == []


def test_changed_baseline_is_changed_candidate(tmp_path: Path) -> None:
    baseline = _candidate(fingerprint="old")
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    decision = decide_source_change(mode="dry_run", candidate_manifest=_candidate(fingerprint="new"), baseline_path=str(baseline_path))
    assert decision["candidate_status"] == "CHANGED_CANDIDATE"
    assert decision["source_changed"] is True
    assert decision["changed_sources"] == ["wdi"]


def test_invalid_candidate_returns_acquisition_failed() -> None:
    decision = decide_source_change(mode="dry_run", candidate_manifest=_candidate(status="acquisition_failed"), baseline_path=None)
    assert decision["candidate_status"] == "ACQUISITION_FAILED"
    assert decision["source_changed"] is None
    assert decision["should_build_downstream"] is False


def test_corrupt_baseline_returns_baseline_invalid(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text("{bad", encoding="utf-8")
    decision = decide_source_change(mode="dry_run", candidate_manifest=_candidate(), baseline_path=str(baseline_path))
    assert decision["candidate_status"] == "BASELINE_INVALID"
    assert decision["source_changed"] is None
    assert decision["should_build_downstream"] is False
