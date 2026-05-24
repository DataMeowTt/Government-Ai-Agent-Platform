from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from config.settings import settings
from jobs.fetch_official_sources import _selected_sources, build_plan_manifest, run_acquisition
from ops.pipeline_run_metadata import build_default_metadata, utc_now_iso
from ops.source_fingerprint import decide_source_change


PLANNED_ACTIONS = [
    "persist_bronze_snapshot_and_manifests",
    "build_silver_candidate",
    "validate_silver_candidate",
    "build_gold_analytics_candidates",
    "run_data_quality_gate",
    "publish_candidate_tables",
    "record_success_freshness",
    "backend_freshness_smoke",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scheduled BigQuery-direct pipeline orchestrator (local plan/dry-run only)."
    )
    parser.add_argument("--mode", choices=["plan", "dry_run"], default="plan")
    parser.add_argument("--run-id", default=settings.run_id)
    parser.add_argument("--run-date", default=settings.run_date)
    parser.add_argument("--source", action="append", default=None, choices=["wdi", "fao_macro", "gmd", "all"])
    parser.add_argument("--runtime-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--previous-success-manifest", default=None)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _planned_actions_payload() -> list[dict[str, Any]]:
    return [{"action": action, "executed": False, "cloud_write": False} for action in PLANNED_ACTIONS]


def _with_finalized_timestamps(metadata: dict[str, Any]) -> dict[str, Any]:
    metadata["finished_at"] = utc_now_iso()
    return metadata


def _build_status(
    *,
    mode: str,
    decision: dict[str, Any],
    force: bool,
) -> tuple[str, bool]:
    reason = str(decision.get("reason") or "")
    candidate_status = str(decision.get("candidate_status") or "")
    source_changed = decision.get("source_changed")

    if candidate_status in {"ACQUISITION_FAILED", "BASELINE_INVALID"}:
        return "FAILED", False
    if mode == "plan":
        return ("PLANNED_CHANGED", False) if source_changed else ("PLANNED_UNCHANGED", False)
    if source_changed:
        return "DRY_RUN_CHANGED", False
    if force and reason in {"candidate_matches_last_successful_baseline", "unchanged"}:
        return "DRY_RUN_CHANGED", True
    return "SKIPPED_UNCHANGED", False


def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime_dir = Path(args.runtime_dir).expanduser().resolve()
    runtime_raw_dir = runtime_dir / "raw"
    runtime_raw_dir.mkdir(parents=True, exist_ok=True)

    selected_sources = _selected_sources(args.source)
    metadata_obj = build_default_metadata(
        run_id=args.run_id,
        run_date=args.run_date,
        execution_mode=args.mode,
        enabled_sources=selected_sources,
        force_requested=bool(args.force),
    )
    metadata = metadata_obj.to_dict()
    metadata["baseline_success_manifest_path"] = args.previous_success_manifest

    try:
        if args.mode == "plan":
            manifest = build_plan_manifest(args, selected_sources)
            decision = decide_source_change(
                mode="plan",
                candidate_manifest=manifest,
                baseline_path=args.previous_success_manifest,
            )
        else:
            manifest, errors = run_acquisition(args=args, selected_sources=selected_sources)
            decision = decide_source_change(
                mode="dry_run",
                candidate_manifest=manifest,
                baseline_path=args.previous_success_manifest,
            )
            if errors:
                _write_json(output_dir / "source_acquisition_errors.json", {"errors": errors})

        _write_json(output_dir / "source_acquisition_manifest.json", manifest)
        _write_json(output_dir / "source_change_decision.json", decision)

        status, force_applied = _build_status(mode=args.mode, decision=decision, force=bool(args.force))
        source_changed = decision.get("source_changed")
        reason = str(decision.get("reason") or "")
        changed_sources = list(decision.get("changed_sources") or [])
        publish_planned = status in {"PLANNED_CHANGED", "DRY_RUN_CHANGED"}

        metadata.update(
            {
                "status": status,
                "source_changed": source_changed,
                "change_reason": reason,
                "candidate_source_manifest_path": str(output_dir / "source_acquisition_manifest.json"),
                "changed_sources": changed_sources,
                "validation_status": "NOT_EXECUTED" if status != "FAILED" else "FAILED",
                "data_quality_status": "NOT_EXECUTED" if status != "FAILED" else "FAILED",
                "bronze_write_planned": publish_planned,
                "bronze_write_performed": False,
                "warehouse_publish_planned": publish_planned,
                "warehouse_publish_performed": False,
                "last_successful_updated": False,
                "last_successful_run_id": None,
                "last_successful_run_date": None,
                "published_at": None,
                "latest_data_year": None,
                "sources_json": None,
                "force_applied": force_applied,
                "planned_actions": _planned_actions_payload() if publish_planned else [],
                "cloud_write": False,
                "publish_performed": False,
            }
        )
        if status == "FAILED":
            metadata["error_message"] = reason or "acquisition_or_validation_failed"

    except Exception as exc:
        metadata.update(
            {
                "status": "FAILED",
                "source_changed": None,
                "change_reason": "exception",
                "validation_status": "FAILED",
                "data_quality_status": "FAILED",
                "error_message": str(exc).splitlines()[0][:500],
            }
        )

    plan_payload = {
        "run_id": args.run_id,
        "run_date": args.run_date,
        "execution_mode": args.mode,
        "status": metadata["status"],
        "source_changed": metadata["source_changed"],
        "change_reason": metadata["change_reason"],
        "publish_performed": False,
        "last_successful_updated": False,
        "baseline_manifest_path": args.previous_success_manifest,
        "force_requested": bool(args.force),
        "force_applied": bool(metadata.get("force_applied")),
        "planned_actions": metadata.get("planned_actions", []),
        "artifacts": {
            "source_acquisition_manifest_path": str(output_dir / "source_acquisition_manifest.json"),
            "source_change_decision_path": str(output_dir / "source_change_decision.json"),
            "pipeline_run_metadata_path": str(output_dir / "pipeline_run_metadata.json"),
        },
    }

    _write_json(output_dir / "scheduled_pipeline_plan.json", plan_payload)
    _write_json(output_dir / "pipeline_run_metadata.json", _with_finalized_timestamps(metadata))
    print(json.dumps({"plan": plan_payload, "metadata": metadata}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if metadata["status"] != "FAILED" else 1


def main(argv: list[str] | None = None) -> int:
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
