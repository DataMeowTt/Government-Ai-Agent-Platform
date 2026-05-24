from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _source_index(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for entry in manifest.get("sources", []):
        name = entry.get("source_name")
        if not name:
            continue
        index[str(name)] = entry
    return index


def _baseline_valid(manifest: dict[str, Any]) -> bool:
    if not isinstance(manifest, dict):
        return False
    sources = manifest.get("sources")
    if not isinstance(sources, list):
        return False
    for entry in sources:
        if not isinstance(entry, dict):
            return False
        if not entry.get("source_name"):
            return False
        if not entry.get("combined_fingerprint"):
            return False
    return True


def load_baseline_manifest(path: str | None) -> tuple[dict[str, Any] | None, str | None]:
    if not path:
        return None, None
    manifest_path = Path(path).expanduser()
    if not manifest_path.exists():
        return None, "baseline_file_not_found"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None, "baseline_json_parse_failed"
    if not _baseline_valid(payload):
        return None, "baseline_manifest_invalid"
    return payload, None


def decide_source_change(*, mode: str, candidate_manifest: dict[str, Any], baseline_path: str | None) -> dict[str, Any]:
    run_id = candidate_manifest.get("run_id")
    run_date = candidate_manifest.get("run_date")

    if mode == "plan":
        return {
            "run_id": run_id,
            "run_date": run_date,
            "candidate_status": "PLANNED",
            "baseline_kind": "local_last_successful_manifest_input",
            "baseline_path": baseline_path if baseline_path else None,
            "source_changed": None,
            "changed_sources": [],
            "reason": "plan_only_no_acquisition",
            "should_build_downstream": False,
        }

    if candidate_manifest.get("status") != "valid":
        return {
            "run_id": run_id,
            "run_date": run_date,
            "candidate_status": "ACQUISITION_FAILED",
            "baseline_kind": "local_last_successful_manifest_input",
            "baseline_path": baseline_path if baseline_path else None,
            "source_changed": None,
            "changed_sources": [],
            "reason": "candidate_acquisition_or_validation_failed",
            "should_build_downstream": False,
        }

    baseline_manifest, baseline_error = load_baseline_manifest(baseline_path)
    if baseline_path and baseline_error:
        return {
            "run_id": run_id,
            "run_date": run_date,
            "candidate_status": "BASELINE_INVALID",
            "baseline_kind": "local_last_successful_manifest_input",
            "baseline_path": baseline_path,
            "source_changed": None,
            "changed_sources": [],
            "reason": baseline_error,
            "should_build_downstream": False,
        }

    candidate_index = _source_index(candidate_manifest)
    if baseline_manifest is None:
        return {
            "run_id": run_id,
            "run_date": run_date,
            "candidate_status": "CHANGED_CANDIDATE",
            "baseline_kind": "local_last_successful_manifest_input",
            "baseline_path": baseline_path if baseline_path else None,
            "source_changed": True,
            "changed_sources": sorted(candidate_index.keys()),
            "reason": "no_last_successful_baseline",
            "should_build_downstream": False,
        }

    baseline_index = _source_index(baseline_manifest)
    changed_sources: list[str] = []
    for source_name in sorted(set(candidate_index.keys()) | set(baseline_index.keys())):
        cand = candidate_index.get(source_name)
        base = baseline_index.get(source_name)
        if not cand or not base:
            changed_sources.append(source_name)
            continue
        if cand.get("combined_fingerprint") != base.get("combined_fingerprint"):
            changed_sources.append(source_name)

    if not changed_sources:
        return {
            "run_id": run_id,
            "run_date": run_date,
            "candidate_status": "SKIPPED_UNCHANGED",
            "baseline_kind": "local_last_successful_manifest_input",
            "baseline_path": baseline_path,
            "source_changed": False,
            "changed_sources": [],
            "reason": "candidate_matches_last_successful_baseline",
            "should_build_downstream": False,
        }

    return {
        "run_id": run_id,
        "run_date": run_date,
        "candidate_status": "CHANGED_CANDIDATE",
        "baseline_kind": "local_last_successful_manifest_input",
        "baseline_path": baseline_path,
        "source_changed": True,
        "changed_sources": changed_sources,
        "reason": "candidate_differs_from_last_successful_baseline",
        "should_build_downstream": False,
    }
