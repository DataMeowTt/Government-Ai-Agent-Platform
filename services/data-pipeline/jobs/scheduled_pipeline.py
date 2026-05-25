from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from config.settings import settings
from jobs.fetch_official_sources import _selected_sources, build_plan_manifest, run_acquisition
from ops.last_successful_manifest import (
    fetch_manifest_text_from_gcs,
    read_latest_success_metadata_rows,
    resolve_baseline_manifest_for_run,
)
from ops.pipeline_run_metadata import build_default_metadata, utc_now_iso
from ops.pipeline_run_metadata_writer import append_pipeline_run_metadata_row
from ops.source_fingerprint import decide_source_change
from sources.gcs_upload import build_upload_plan, execute_upload_plan
from sources.gcs_runtime_client import verify_gcs_object_matches_local_file
from sources.official_bronze import materialize_official_bronze_snapshot
from warehouse.bigquery_silver_load_plan import build_silver_load_plan
from warehouse.bigquery_silver_loader import (
    stage_and_validate_silver_candidate,
    promote_silver_candidate,
)
from warehouse.bigquery_warehouse_publish import (
    promote_validated_candidate,
    stage_and_validate_candidate,
)
from warehouse.bigquery_warehouse_rebuild import run_warehouse_rebuild
from warehouse.candidate_data_quality_gate import run_candidate_data_quality_gate
from warehouse.bigquery_warehouse_validation import get_table_contract_columns, load_table_contract
from warehouse.bigquery_recovery import (
    PRODUCTION_TABLE_ORDER,
    RecoveryCollisionError,
    prepare_recovery_backups,
    restore_production_tables,
    retention_days_from_env,
)


PLANNED_ACTIONS = [
    "persist_bronze_snapshot_and_manifests",
    "upload_bronze_snapshot_and_manifests",
    "build_silver_candidate",
    "stage_validate_silver_candidate",
    "build_gold_analytics_candidates",
    "stage_validate_gold_analytics_candidates",
    "promote_silver_production",
    "promote_gold_analytics_production",
    "prepare_recovery_backups",
    "record_success_freshness",
]

BLOCKED_STATUS = "BLOCKED_APPROVAL_REQUIRED"
STATUS_SUCCESS = "SUCCESS"
STATUS_PARTIAL_FAILED = "PARTIAL_FAILED"


PIPELINE_RUN_METADATA_COLUMNS = (
    "run_id",
    "run_date",
    "execution_mode",
    "status",
    "started_at",
    "finished_at",
    "enabled_sources",
    "source_changed",
    "change_reason",
    "candidate_source_manifest_path",
    "baseline_success_manifest_path",
    "changed_sources",
    "validation_status",
    "data_quality_status",
    "bronze_write_planned",
    "bronze_write_performed",
    "warehouse_publish_planned",
    "warehouse_publish_performed",
    "last_successful_updated",
    "last_successful_run_id",
    "last_successful_run_date",
    "published_at",
    "latest_data_year",
    "sources_json",
    "error_message",
    "force_requested",
    "force_applied",
    "planned_actions",
    "cloud_write",
    "publish_performed",
)


def _metadata_storage_row(metadata: dict[str, Any]) -> dict[str, Any]:
    return {column: metadata.get(column) for column in PIPELINE_RUN_METADATA_COLUMNS}


def _tail_nonempty_lines(text: str, *, max_lines: int = 20) -> list[str]:
    lines = [line.strip() for line in str(text or "").splitlines() if line and line.strip()]
    if len(lines) <= max_lines:
        return lines
    return lines[-max_lines:]


def _is_low_signal_subprocess_line(line: str) -> bool:
    lowered = line.strip().lower()
    if not lowered:
        return True
    if lowered.startswith("warning: using incubator modules"):
        return True
    if lowered.startswith("using spark's default log4j profile"):
        return True
    if lowered.startswith("setting default log level to"):
        return True
    if lowered.startswith("[stage "):
        return True
    return False


def _pick_subprocess_failure_reason(stderr_tail: list[str], stdout_tail: list[str]) -> str:
    combined_tail = [*stderr_tail, *stdout_tail]
    for line in reversed(combined_tail):
        if not _is_low_signal_subprocess_line(line):
            return line
    for line in reversed(combined_tail):
        if line.strip():
            return line.strip()
    return "subprocess returned non-zero exit code"


def _format_exception_message(exc: Exception, *, max_length: int = 500) -> str:
    if isinstance(exc, KeyError):
        return repr(exc)[:max_length]
    message = str(exc).splitlines()[0].strip() if str(exc) else ""
    if not message:
        message = repr(exc)
    return message[:max_length]


def _traceback_tail(exc: Exception, *, max_lines: int = 16, max_chars: int = 2500) -> str:
    lines = [line.rstrip() for line in traceback.format_exception(type(exc), exc, exc.__traceback__) if line and line.strip()]
    tail = "\n".join(lines[-max_lines:]).strip()
    if len(tail) > max_chars:
        tail = tail[-max_chars:]
    return tail


def _apply_failure_diagnostics(
    metadata: dict[str, Any],
    *,
    failed_step: str | None,
    exc: Exception,
) -> None:
    metadata["failed_step"] = failed_step
    metadata["exception_type"] = type(exc).__name__
    metadata["error_message"] = _format_exception_message(exc)
    metadata["traceback_tail"] = _traceback_tail(exc)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scheduled BigQuery-direct pipeline orchestrator with plan/dry-run/execute modes."
    )
    parser.add_argument("--mode", choices=["plan", "dry_run", "execute"], default="plan")
    parser.add_argument("--run-id", default=settings.run_id)
    parser.add_argument("--run-date", default=settings.run_date)
    parser.add_argument("--source", action="append", default=None, choices=["wdi", "fao_macro", "gmd", "all"])
    parser.add_argument("--runtime-dir", required=True)
    parser.add_argument("--runtime-raw-dir", default=None)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--previous-success-manifest", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--project-id", default="western-pivot-452008-a6")
    parser.add_argument("--location", default="asia-southeast1")
    parser.add_argument("--gcs-bucket", default="western-pivot-452008-a6-gov-ai-economic-data")
    parser.add_argument(
        "--ops-metadata-table",
        default="western-pivot-452008-a6.gov_ai_ops.pipeline_run_metadata",
    )
    parser.add_argument("--silver-output-format", default="parquet", choices=["parquet", "csv"])
    parser.add_argument("--silver-source", default="all", choices=["all", "wdi", "gmd", "fao_macro"])
    return parser.parse_args(argv)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _planned_actions_payload() -> list[dict[str, Any]]:
    return [{"action": action, "executed": False, "cloud_write": False, "status": "planned"} for action in PLANNED_ACTIONS]


def _safe_identifier(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", str(value or "").strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "run"


def _approval_granted(env_name: str) -> bool:
    return str(os.getenv(env_name, "false")).strip().lower() == "true"


def _resolve_runtime_raw_dir(args: argparse.Namespace, runtime_dir: Path) -> Path:
    if args.runtime_raw_dir:
        return Path(args.runtime_raw_dir).expanduser().resolve()
    return runtime_dir / "raw"


def _build_acquisition_blocked_manifest(args: argparse.Namespace, selected_sources: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = build_plan_manifest(args, selected_sources)
    manifest["status"] = "acquisition_failed"
    manifest["sources"] = [
        {
            "source_name": source_name,
            "validation_status": "invalid",
            "error_message": "network_not_allowed",
            "required_files": [],
            "present_files": [],
            "missing_files": [],
        }
        for source_name in selected_sources
    ]
    errors = [{"source_name": source_name, "error": "network_not_allowed"} for source_name in selected_sources]
    return manifest, errors


def _build_status(mode: str, decision: dict[str, Any], *, force: bool) -> tuple[str, bool]:
    candidate_status = str(decision.get("candidate_status") or "")
    source_changed = decision.get("source_changed")
    reason = str(decision.get("reason") or "")

    if candidate_status == "ACQUISITION_FAILED":
        return "ACQUISITION_FAILED", False
    if candidate_status == "BASELINE_INVALID":
        return "BASELINE_INVALID", False

    if mode == "plan":
        return ("PLANNED_CHANGED", False) if source_changed else ("PLANNED_UNCHANGED", False)
    if mode == "dry_run":
        if source_changed:
            return "DRY_RUN_CHANGED", False
        if force and reason in {"candidate_matches_last_successful_baseline", "unchanged"}:
            return "DRY_RUN_CHANGED", True
        return "SKIPPED_UNCHANGED", False
    if source_changed:
        return "CHANGED_CANDIDATE", False
    if force and reason in {"candidate_matches_last_successful_baseline", "unchanged"}:
        return "CHANGED_CANDIDATE", True
    return "SKIPPED_UNCHANGED", False


def _run_build_silver_candidate(
    *,
    run_id: str,
    run_date: str,
    output_dir: Path,
    source: str,
    output_format: str,
    wdi_path: Path,
    gmd_path: Path,
    fao_macro_path: Path,
) -> dict[str, Any]:
    command = [
        sys.executable,
        "-m",
        "jobs.build_silver",
        "--source",
        source,
        "--run-id",
        run_id,
        "--run-date",
        run_date,
        "--output-dir",
        str(output_dir),
        "--output-format",
        output_format,
        "--wdi-path",
        str(wdi_path),
        "--gmd-path",
        str(gmd_path),
        "--fao-macro-path",
        str(fao_macro_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        stderr_tail = _tail_nonempty_lines(result.stderr, max_lines=20)
        stdout_tail = _tail_nonempty_lines(result.stdout, max_lines=20)
        reason = _pick_subprocess_failure_reason(stderr_tail, stdout_tail)
        raise RuntimeError(
            "build_silver failed "
            f"(exit_code={result.returncode}; reason={reason}; "
            f"stderr_tail={stderr_tail}; stdout_tail={stdout_tail})"
        )
    manifest_path = output_dir / "silver_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"silver_manifest.json not found after build: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "command": command,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "manifest_path": str(manifest_path),
        "manifest": manifest,
        "silver_output_path": str((output_dir / "silver_indicators").resolve()),
    }


def _required_columns_for_table(contract: dict[str, Any], dataset: str, table_name: str) -> list[str]:
    if dataset == "gov_ai_gold":
        columns = get_table_contract_columns(contract, "gold", table_name)
    else:
        columns = get_table_contract_columns(contract, "analytics", table_name)
    if columns:
        return columns
    if table_name == "analytics_clusters":
        return ["country_code", "country", "year", "cluster_id", "latest_valid_year", "run_id", "run_date", "loaded_at"]
    return ["country_code", "country", "year", "run_id", "run_date", "loaded_at"]


def _resolve_contract_path() -> Path:
    current = Path(__file__).resolve()
    candidates = [current.parent, *current.parents]
    for candidate in candidates:
        contract_path = candidate / "contracts" / "table_contract.yaml"
        if contract_path.exists():
            return contract_path
    raise FileNotFoundError(
        "Unable to resolve contracts/table_contract.yaml from "
        f"{current}"
    )


@dataclass
class Dependencies:
    resolve_baseline: Callable[..., dict[str, Any]] = resolve_baseline_manifest_for_run
    build_silver_candidate: Callable[..., dict[str, Any]] = _run_build_silver_candidate
    build_official_bronze: Callable[..., dict[str, Any]] = materialize_official_bronze_snapshot
    build_upload_plan_fn: Callable[..., dict[str, Any]] = build_upload_plan
    execute_upload_plan_fn: Callable[[dict[str, Any]], dict[str, Any]] = execute_upload_plan
    verify_uploaded_source_manifest: Callable[..., dict[str, Any]] = verify_gcs_object_matches_local_file
    build_silver_load_plan_fn: Callable[..., dict[str, Any]] = build_silver_load_plan
    stage_silver_candidate: Callable[..., dict[str, Any]] = stage_and_validate_silver_candidate
    promote_silver_candidate_fn: Callable[..., dict[str, Any]] = promote_silver_candidate
    rebuild_warehouse: Callable[..., dict[str, Any]] = run_warehouse_rebuild
    stage_warehouse_candidate: Callable[..., Any] = stage_and_validate_candidate
    promote_warehouse_candidate: Callable[..., Any] = promote_validated_candidate
    run_data_quality_gate: Callable[..., dict[str, Any]] = run_candidate_data_quality_gate
    prepare_recovery_backups_fn: Callable[..., dict[str, Any]] = prepare_recovery_backups
    restore_production_tables_fn: Callable[..., dict[str, Any]] = restore_production_tables
    recovery_retention_days: Callable[..., int] = retention_days_from_env
    append_metadata_row: Callable[..., dict[str, Any]] = append_pipeline_run_metadata_row
    read_success_metadata_rows: Callable[..., list[dict[str, Any]]] = read_latest_success_metadata_rows
    fetch_manifest_text: Callable[[str], str | bytes] = fetch_manifest_text_from_gcs
    env_getter: Callable[[str], str | None] = os.getenv


def run(argv: list[str] | None = None, *, deps: Dependencies | None = None) -> int:
    dependencies = deps or Dependencies()
    args = parse_args(argv)

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime_dir = Path(args.runtime_dir).expanduser().resolve()
    runtime_dir.mkdir(parents=True, exist_ok=True)
    runtime_raw_dir = _resolve_runtime_raw_dir(args, runtime_dir)
    runtime_raw_dir.mkdir(parents=True, exist_ok=True)
    baseline_runtime_dir = runtime_dir / "baseline"
    baseline_runtime_dir.mkdir(parents=True, exist_ok=True)

    selected_sources = _selected_sources(args.source)
    metadata_obj = build_default_metadata(
        run_id=args.run_id,
        run_date=args.run_date,
        execution_mode=args.mode,
        enabled_sources=selected_sources,
        force_requested=bool(args.force),
    )
    metadata = metadata_obj.to_dict()
    steps: list[dict[str, Any]] = []
    touched_production_tables: list[str] = []
    candidate_validations: list[dict[str, Any]] = []
    promoted_production_tables: list[str] = []
    recovery_backups: dict[str, Any] | None = None
    restore_attempt: dict[str, Any] | None = None
    publish_performed = False
    baseline_path_for_compare = args.previous_success_manifest
    active_step: str | None = None

    def add_step(name: str, status: str, *, executed: bool, cloud_write: bool, details: dict[str, Any] | None = None) -> None:
        steps.append(
            {
                "step": name,
                "status": status,
                "executed": executed,
                "cloud_write": cloud_write,
                "details": details or {},
            }
        )

    def set_active_step(name: str) -> None:
        nonlocal active_step
        active_step = name

    baseline_result = {
        "status": "NO_BASELINE",
        "reason": "not_required",
        "baseline_path": args.previous_success_manifest,
        "baseline_source_uri": args.previous_success_manifest,
    }
    try:
        if args.mode == "execute":
            set_active_step("resolve_baseline_manifest")
            resolve_kwargs: dict[str, Any] = {
                "runtime_dir": baseline_runtime_dir,
                "explicit_baseline_path": args.previous_success_manifest,
            }
            if not args.previous_success_manifest:
                resolve_kwargs["metadata_reader"] = lambda: dependencies.read_success_metadata_rows(
                    project_id=args.project_id,
                    table_id=args.ops_metadata_table,
                )
                resolve_kwargs["manifest_fetcher"] = dependencies.fetch_manifest_text
            baseline_result = dependencies.resolve_baseline(**resolve_kwargs)
            baseline_path_for_compare = baseline_result.get("baseline_path")
        metadata["baseline_success_manifest_path"] = baseline_result.get("baseline_source_uri")
        add_step("resolve_baseline_manifest", baseline_result["status"], executed=True, cloud_write=False, details=baseline_result)

        if args.mode == "plan":
            manifest = build_plan_manifest(args, selected_sources)
            decision = decide_source_change(
                mode="plan",
                candidate_manifest=manifest,
                baseline_path=baseline_result.get("baseline_path"),
            )
        else:
            if not args.allow_network:
                manifest, errors = _build_acquisition_blocked_manifest(args, selected_sources)
                _write_json(output_dir / "source_acquisition_errors.json", {"errors": errors})
                add_step(
                    "acquire_official_sources",
                    "ACQUISITION_BLOCKED_NETWORK_NOT_ALLOWED",
                    executed=False,
                    cloud_write=False,
                    details={"allow_network": False},
                )
            else:
                set_active_step("acquire_official_sources")
                acquisition_args = argparse.Namespace(**{**vars(args), "runtime_raw_dir": str(runtime_raw_dir)})
                manifest, errors = run_acquisition(args=acquisition_args, selected_sources=selected_sources)
                add_step(
                    "acquire_official_sources",
                    "ACQUIRED" if not errors else "ACQUISITION_PARTIAL_FAILED",
                    executed=True,
                    cloud_write=False,
                    details={"error_count": len(errors)},
                )
                if errors:
                    _write_json(output_dir / "source_acquisition_errors.json", {"errors": errors})
            decision = decide_source_change(
                mode="dry_run",
                candidate_manifest=manifest,
                baseline_path=baseline_path_for_compare,
            )
            if args.mode == "execute" and baseline_result.get("status") == "BASELINE_INVALID":
                decision = {
                    "run_id": args.run_id,
                    "run_date": args.run_date,
                    "candidate_status": "BASELINE_INVALID",
                    "baseline_kind": "latest_success_metadata",
                    "baseline_path": baseline_result.get("baseline_source_uri"),
                    "source_changed": None,
                    "changed_sources": [],
                    "reason": baseline_result.get("reason", "baseline_manifest_invalid"),
                    "should_build_downstream": False,
                }

        _write_json(output_dir / "source_acquisition_manifest.json", manifest)
        _write_json(output_dir / "source_change_decision.json", decision)
        status, force_applied = _build_status(args.mode, decision, force=bool(args.force))

        source_changed = decision.get("source_changed")
        changed_sources = list(decision.get("changed_sources") or [])
        reason = str(decision.get("reason") or "")
        publish_planned = status in {"PLANNED_CHANGED", "DRY_RUN_CHANGED", "CHANGED_CANDIDATE"}

        metadata.update(
            {
                "status": status,
                "source_changed": source_changed,
                "change_reason": reason,
                "candidate_source_manifest_path": str(output_dir / "source_acquisition_manifest.json"),
                "changed_sources": changed_sources,
                "validation_status": "NOT_EXECUTED",
                "data_quality_status": "NOT_EXECUTED",
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
                "error_message": None,
                "failed_step": None,
                "exception_type": None,
                "traceback_tail": None,
                "force_applied": force_applied,
                "planned_actions": _planned_actions_payload() if publish_planned else [],
                "cloud_write": False,
                "publish_performed": False,
            }
        )

        if status in {"ACQUISITION_FAILED", "BASELINE_INVALID"}:
            metadata["validation_status"] = "FAILED"
            metadata["data_quality_status"] = "FAILED"
            metadata["error_message"] = reason or status.lower()
        elif args.mode in {"plan", "dry_run"} or status == "SKIPPED_UNCHANGED":
            metadata["validation_status"] = "NOT_EXECUTED"
            metadata["data_quality_status"] = "NOT_EXECUTED"
        elif args.mode == "execute" and status == "CHANGED_CANDIDATE":
            bronze_output_dir = runtime_dir / "official_bronze"
            silver_output_dir = runtime_dir / "silver_candidate"
            warehouse_output_dir = runtime_dir / "warehouse_candidate"
            run_token = _safe_identifier(args.run_id)

            set_active_step("materialize_official_bronze")
            bronze_payload = dependencies.build_official_bronze(
                acquisition_manifest=manifest,
                runtime_raw_dir=runtime_raw_dir,
                output_dir=bronze_output_dir,
                run_id=args.run_id,
                run_date=args.run_date,
            )
            add_step(
                "materialize_official_bronze",
                "MATERIALIZED",
                executed=True,
                cloud_write=False,
                details={"source_manifest_path": bronze_payload["source_manifest_path"]},
            )

            if not _approval_granted("CLOUD_WRITE_APPROVED"):
                metadata["status"] = BLOCKED_STATUS
                metadata["change_reason"] = "missing_cloud_write_approval"
                metadata["error_message"] = "CLOUD_WRITE_APPROVED must be true"
                metadata["validation_status"] = "NOT_EXECUTED"
                metadata["data_quality_status"] = "NOT_EXECUTED"
                add_step("upload_bronze_snapshot_and_manifests", "BLOCKED_APPROVAL_REQUIRED", executed=False, cloud_write=False)
            else:
                set_active_step("upload_bronze_snapshot_and_manifests")
                upload_plan = dependencies.build_upload_plan_fn(
                    output_dir=bronze_output_dir,
                    bucket=args.gcs_bucket,
                    run_id=args.run_id,
                    run_date=args.run_date,
                    dry_run=False,
                    cloud_approved=True,
                    run_scoped=True,
                    atomic_create_only=True,
                )
                set_active_step("upload_bronze_snapshot_and_manifests")
                upload_result = dependencies.execute_upload_plan_fn(upload_plan)
                upload_status = str(upload_result.get("status") or "").upper()
                upload_cloud_write_performed = bool(upload_result.get("cloud_write_performed")) or int(upload_result.get("uploaded_count") or 0) > 0
                metadata["bronze_write_performed"] = upload_cloud_write_performed
                metadata["cloud_write"] = upload_cloud_write_performed
                add_step(
                    "upload_bronze_snapshot_and_manifests",
                    upload_status or "FAILED",
                    executed=True,
                    cloud_write=upload_cloud_write_performed,
                    details=upload_result,
                )
                if upload_status != "UPLOADED":
                    metadata.update(
                        {
                            "status": "VALIDATION_FAILED",
                            "validation_status": "FAILED",
                            "data_quality_status": "NOT_EXECUTED",
                            "publish_performed": False,
                            "warehouse_publish_performed": False,
                            "last_successful_updated": False,
                            "published_at": None,
                            "latest_data_year": None,
                            "sources_json": None,
                            "error_message": str(upload_result.get("error_message") or "gcs_upload_failed"),
                        }
                    )
                    raise RuntimeError("gcs_upload_failed")

                metadata["candidate_source_manifest_path"] = str(upload_plan["source_manifest_path"])

                manifest_upload_entry = next(
                    (
                        item
                        for item in upload_plan.get("objects", [])
                        if str(item.get("artifact_type") or "") == "source_manifest"
                        and str(item.get("target_gcs_uri") or "") == str(upload_plan.get("source_manifest_path") or "")
                    ),
                    None,
                )
                if manifest_upload_entry is None:
                    raise RuntimeError("source_manifest upload entry not found in upload plan")

                set_active_step("verify_uploaded_source_manifest")
                verify_payload = dependencies.verify_uploaded_source_manifest(
                    local_path=manifest_upload_entry["local_path"],
                    target_gcs_uri=manifest_upload_entry["target_gcs_uri"],
                )
                verify_status = str(verify_payload.get("status") or "").upper()
                add_step(
                    "verify_uploaded_source_manifest",
                    verify_status or "FAILED",
                    executed=True,
                    cloud_write=False,
                    details=verify_payload,
                )
                if verify_status != "VERIFIED":
                    metadata.update(
                        {
                            "status": "VALIDATION_FAILED",
                            "validation_status": "FAILED",
                            "data_quality_status": "NOT_EXECUTED",
                            "publish_performed": False,
                            "warehouse_publish_performed": False,
                            "last_successful_updated": False,
                            "published_at": None,
                            "latest_data_year": None,
                            "sources_json": None,
                            "error_message": "uploaded_source_manifest_verification_failed",
                        }
                    )
                    raise RuntimeError("uploaded source_manifest verification failed")

                if not _approval_granted("BIGQUERY_WRITE_APPROVED"):
                    metadata["status"] = BLOCKED_STATUS
                    metadata["change_reason"] = "missing_bigquery_write_approval"
                    metadata["error_message"] = "BIGQUERY_WRITE_APPROVED must be true"
                    add_step("stage_validate_silver_candidate", "BLOCKED_APPROVAL_REQUIRED", executed=False, cloud_write=False)
                else:
                    wdi_path = runtime_raw_dir / "worldBank" / "WDICSV.csv"
                    gmd_path = runtime_raw_dir / "gmd" / "GMD.csv"
                    fao_path = (
                        runtime_raw_dir
                        / "Macro-Statistics_Key_Indicators_E_All_Data_(Normalized)"
                        / "Macro-Statistics_Key_Indicators_E_All_Data_(Normalized).csv"
                    )
                    for required_path in (wdi_path, gmd_path, fao_path):
                        if not required_path.exists():
                            raise FileNotFoundError(f"Official runtime input missing: {required_path}")

                    set_active_step("build_silver_candidate")
                    silver_build = dependencies.build_silver_candidate(
                        run_id=args.run_id,
                        run_date=args.run_date,
                        output_dir=silver_output_dir,
                        source=args.silver_source,
                        output_format=args.silver_output_format,
                        wdi_path=wdi_path,
                        gmd_path=gmd_path,
                        fao_macro_path=fao_path,
                    )
                    add_step(
                        "build_silver_candidate",
                        "BUILT",
                        executed=True,
                        cloud_write=False,
                        details={"silver_manifest_path": silver_build["manifest_path"]},
                    )

                    set_active_step("build_silver_load_plan")
                    silver_plan = dependencies.build_silver_load_plan_fn(
                        silver_output_dir=silver_build["silver_output_path"],
                        silver_manifest=silver_build["manifest_path"],
                        project_id=args.project_id,
                        dataset="gov_ai_silver",
                        table="silver_indicators",
                        location=args.location,
                        run_id=args.run_id,
                        run_date=args.run_date,
                    )
                    silver_plan_path = warehouse_output_dir / "silver_load_plan.json"
                    _write_json(silver_plan_path, silver_plan)

                    set_active_step("stage_validate_silver_candidate")
                    silver_stage_payload = dependencies.stage_silver_candidate(
                        plan=silver_plan,
                        load_plan_path=str(silver_plan_path),
                        project_id=args.project_id,
                        dataset="gov_ai_silver",
                        table="silver_indicators",
                        location=args.location,
                        approval_env="BIGQUERY_WRITE_APPROVED",
                        output_dir=warehouse_output_dir / "silver_stage",
                        staging_table=f"silver_indicators_staging_run_{run_token}",
                    )
                    silver_candidate_table_id = silver_stage_payload["result"]["staging_table_id"]
                    silver_expected_rows = int(silver_stage_payload["validation"]["local_validation"]["row_count"])
                    add_step(
                        "stage_validate_silver_candidate",
                        "VALIDATED",
                        executed=True,
                        cloud_write=True,
                        details={"candidate_table_id": silver_candidate_table_id, "row_count": silver_expected_rows},
                    )

                    if not _approval_granted("BIGQUERY_WAREHOUSE_WRITE_APPROVED"):
                        metadata["status"] = BLOCKED_STATUS
                        metadata["change_reason"] = "missing_bigquery_warehouse_write_approval"
                        metadata["error_message"] = "BIGQUERY_WAREHOUSE_WRITE_APPROVED must be true"
                        add_step("stage_validate_gold_analytics_candidates", "BLOCKED_APPROVAL_REQUIRED", executed=False, cloud_write=False)
                    else:
                        set_active_step("build_gold_analytics_candidates")
                        rebuild_payload = dependencies.rebuild_warehouse(
                            project_id=args.project_id,
                            location=args.location,
                            silver_table_id=silver_candidate_table_id,
                            output_dir=warehouse_output_dir,
                            expected_silver_row_count=None,
                        )
                        add_step("build_gold_analytics_candidates", "BUILT", executed=True, cloud_write=False)

                        summary_by_table = {
                            item["table_name"]: item for item in rebuild_payload.get("gold_summary", [])
                        }
                        summary_by_table.update(
                            {item["table_name"]: item for item in rebuild_payload.get("analytics_summary", [])}
                        )
                        contract = load_table_contract(_resolve_contract_path())
                        staged_candidates: list[Any] = []
                        set_active_step("stage_validate_gold_analytics_candidates")
                        for table_plan in list(rebuild_payload["publish_plan"]["tables"]):
                            table_name = str(table_plan["production_table"])
                            dataset = str(table_plan["dataset"])
                            parquet_path = Path(summary_by_table[table_name]["parquet_path"])
                            candidate = dependencies.stage_warehouse_candidate(
                                project_id=args.project_id,
                                location=args.location,
                                dataset=dataset,
                                staging_table=str(table_plan["staging_table"]),
                                production_table=table_name,
                                parquet_path=parquet_path,
                                expected_required_columns=_required_columns_for_table(contract, dataset, table_name),
                                local_row_count=int(table_plan["row_count"]),
                            )
                            staged_candidates.append(candidate)
                            candidate_validations.append(
                                {
                                    "dataset": dataset,
                                    "production_table": table_name,
                                    "staging_table": str(table_plan["staging_table"]),
                                    "staging_row_count": int(table_plan["row_count"]),
                                }
                            )
                        add_step(
                            "stage_validate_gold_analytics_candidates",
                            "VALIDATED",
                            executed=True,
                            cloud_write=True,
                            details={"candidate_count": len(staged_candidates)},
                        )

                        expected_candidate_tables = ["silver_indicators"] + [
                            str(item["production_table"]) for item in list(rebuild_payload["publish_plan"]["tables"])
                        ]
                        candidate_artifacts: dict[str, Any] = {"silver_indicators": silver_build["silver_output_path"]}
                        for table_plan in list(rebuild_payload["publish_plan"]["tables"]):
                            table_name = str(table_plan["production_table"])
                            candidate_artifacts[table_name] = str(summary_by_table[table_name]["parquet_path"])

                        set_active_step("run_candidate_data_quality_gate")
                        quality_gate_payload = dependencies.run_data_quality_gate(
                            expected_tables=expected_candidate_tables,
                            candidate_artifacts=candidate_artifacts,
                            output_path=warehouse_output_dir / "candidate_data_quality_gate.json",
                            contract_payload=contract,
                        )
                        quality_status = str(quality_gate_payload.get("status") or "FAILED").upper()
                        if quality_status != "PASSED":
                            metadata.update(
                                {
                                    "status": "VALIDATION_FAILED",
                                    "validation_status": "FAILED",
                                    "data_quality_status": "FAILED",
                                    "error_message": "candidate_data_quality_gate_failed",
                                }
                            )
                            add_step(
                                "run_candidate_data_quality_gate",
                                "FAILED",
                                executed=True,
                                cloud_write=False,
                                details={"error_count": len(quality_gate_payload.get("errors") or [])},
                            )
                        else:
                            metadata["validation_status"] = "PASSED"
                            metadata["data_quality_status"] = "PASSED"
                            add_step(
                                "run_candidate_data_quality_gate",
                                "PASSED",
                                executed=True,
                                cloud_write=False,
                                details={"checked_table_count": len(quality_gate_payload.get("checked_tables") or [])},
                            )

                            if not _approval_granted("BIGQUERY_OPS_WRITE_APPROVED"):
                                metadata["status"] = BLOCKED_STATUS
                                metadata["change_reason"] = "missing_bigquery_ops_write_approval"
                                metadata["error_message"] = "BIGQUERY_OPS_WRITE_APPROVED must be true"
                                add_step("record_success_freshness", "BLOCKED_APPROVAL_REQUIRED", executed=False, cloud_write=False)
                            else:
                                try:
                                    ordered_production_tables = [
                                        f"{args.project_id}.gov_ai_silver.silver_indicators",
                                        *[
                                            f"{args.project_id}.{str(item['dataset'])}.{str(item['production_table'])}"
                                            for item in list(rebuild_payload["publish_plan"]["tables"])
                                        ],
                                    ]
                                    if args.project_id == "western-pivot-452008-a6":
                                        if ordered_production_tables != PRODUCTION_TABLE_ORDER:
                                            raise RuntimeError(
                                                "production_table_order_mismatch: expected exactly all canonical scheduled production targets"
                                            )

                                    set_active_step("prepare_recovery_backups")
                                    retention_days = dependencies.recovery_retention_days(dependencies.env_getter)
                                    recovery_backups = dependencies.prepare_recovery_backups_fn(
                                        project_id=args.project_id,
                                        location=args.location,
                                        production_table_ids=ordered_production_tables,
                                        run_id=args.run_id,
                                        retention_days=retention_days,
                                        approval_env="BIGQUERY_WAREHOUSE_WRITE_APPROVED",
                                        env_getter=dependencies.env_getter,
                                    )
                                    add_step(
                                        "prepare_recovery_backups",
                                        str(recovery_backups.get("status") or "RECOVERY_READY"),
                                        executed=True,
                                        cloud_write=True,
                                        details={
                                            "backup_count": len(recovery_backups.get("backups") or []),
                                            "retention_days": recovery_backups.get("retention_days"),
                                        },
                                    )

                                    set_active_step("promote_silver_production")
                                    silver_promotion = dependencies.promote_silver_candidate_fn(
                                        project_id=args.project_id,
                                        dataset="gov_ai_silver",
                                        table="silver_indicators",
                                        location=args.location,
                                        candidate_table_id=silver_candidate_table_id,
                                        expected_row_count=silver_expected_rows,
                                        approval_env="BIGQUERY_WRITE_APPROVED",
                                    )
                                    touched_production_tables.append(silver_promotion["target_table_id"])
                                    promoted_production_tables.append(silver_promotion["target_table_id"])
                                    add_step(
                                        "promote_silver_production",
                                        "PROMOTED",
                                        executed=True,
                                        cloud_write=True,
                                        details={"target_table_id": silver_promotion["target_table_id"]},
                                    )

                                    warehouse_writes: list[dict[str, Any]] = []
                                    set_active_step("promote_gold_analytics_production")
                                    for candidate in staged_candidates:
                                        promoted = dependencies.promote_warehouse_candidate(
                                            project_id=args.project_id,
                                            location=args.location,
                                            candidate=candidate,
                                        )
                                        touched_production_tables.append(promoted.production_table_id)
                                        promoted_production_tables.append(promoted.production_table_id)
                                        warehouse_writes.append(
                                            {
                                                "dataset": promoted.dataset,
                                                "production_table_id": promoted.production_table_id,
                                                "staging_table_id": promoted.staging_table_id,
                                            }
                                        )
                                    add_step(
                                        "promote_gold_analytics_production",
                                        "PROMOTED",
                                        executed=True,
                                        cloud_write=True,
                                        details={"table_count": len(warehouse_writes)},
                                    )

                                    latest_data_year = int(rebuild_payload["silver_preflight"]["year_max"])
                                    sources_json = json.dumps(manifest.get("sources", []), ensure_ascii=False, sort_keys=True)
                                    metadata.update(
                                        {
                                            "status": STATUS_SUCCESS,
                                            "validation_status": "PASSED",
                                            "data_quality_status": "PASSED",
                                            "warehouse_publish_performed": True,
                                            "publish_performed": True,
                                            "last_successful_updated": True,
                                            "published_at": utc_now_iso(),
                                            "latest_data_year": latest_data_year,
                                            "sources_json": sources_json,
                                            "cloud_write": True,
                                        }
                                    )

                                    metadata["finished_at"] = utc_now_iso()
                                    set_active_step("record_success_freshness")
                                    metadata_write = dependencies.append_metadata_row(
                                        row=_metadata_storage_row(metadata),
                                        project_id=args.project_id,
                                        env_getter=dependencies.env_getter,
                                        approval_env="BIGQUERY_OPS_WRITE_APPROVED",
                                    )
                                    publish_performed = True
                                    add_step(
                                        "record_success_freshness",
                                        "WRITTEN",
                                        executed=True,
                                        cloud_write=True,
                                        details={"table_id": metadata_write["table_id"]},
                                    )
                                except RecoveryCollisionError as exc:
                                    metadata.update(
                                        {
                                            "status": "FAILED",
                                            "publish_performed": False,
                                            "warehouse_publish_performed": False,
                                            "last_successful_updated": False,
                                            "published_at": None,
                                            "latest_data_year": None,
                                            "sources_json": None,
                                            "validation_status": "FAILED",
                                            "data_quality_status": "FAILED",
                                        }
                                    )
                                    _apply_failure_diagnostics(metadata, failed_step=active_step, exc=exc)
                                except Exception as exc:
                                    triggering_step = active_step
                                    if recovery_backups and promoted_production_tables:
                                        set_active_step("restore_production_from_recovery")
                                        restore_attempt = dependencies.restore_production_tables_fn(
                                            project_id=args.project_id,
                                            location=args.location,
                                            touched_production_tables=promoted_production_tables,
                                            backup_payload=recovery_backups,
                                            approval_env="BIGQUERY_WAREHOUSE_WRITE_APPROVED",
                                            env_getter=dependencies.env_getter,
                                        )
                                        add_step(
                                            "restore_production_from_recovery",
                                            str(restore_attempt.get("status") or "RESTORE_FAILED"),
                                            executed=True,
                                            cloud_write=True,
                                            details=restore_attempt,
                                        )
                                    metadata.update(
                                        {
                                            "status": STATUS_PARTIAL_FAILED if touched_production_tables else "FAILED",
                                            "publish_performed": False,
                                            "warehouse_publish_performed": False,
                                            "last_successful_updated": False,
                                            "published_at": None,
                                            "latest_data_year": None,
                                            "sources_json": None,
                                            "validation_status": "FAILED",
                                            "data_quality_status": "FAILED",
                                        }
                                    )
                                    _apply_failure_diagnostics(metadata, failed_step=triggering_step, exc=exc)

    except Exception as exc:
        if metadata.get("status") not in {STATUS_SUCCESS, BLOCKED_STATUS, STATUS_PARTIAL_FAILED, "VALIDATION_FAILED"}:
            _apply_failure_diagnostics(metadata, failed_step=active_step, exc=exc)
            metadata.update(
                {
                    "status": "FAILED",
                    "source_changed": metadata.get("source_changed"),
                    "change_reason": metadata.get("change_reason") or "exception",
                    "validation_status": "FAILED",
                    "data_quality_status": "FAILED",
                }
            )
        elif not metadata.get("exception_type"):
            metadata["failed_step"] = active_step
            metadata["exception_type"] = type(exc).__name__
            metadata["traceback_tail"] = _traceback_tail(exc)
            if isinstance(exc, KeyError):
                metadata["error_message"] = _format_exception_message(exc)

    metadata["finished_at"] = utc_now_iso()
    metadata["planned_actions"] = steps if steps else metadata.get("planned_actions", [])
    metadata["recovery_backups"] = recovery_backups or {}
    metadata["restore_attempt"] = restore_attempt or {}

    final_status = str(metadata.get("status") or "FAILED")
    if final_status in {BLOCKED_STATUS, "SKIPPED_UNCHANGED", "DRY_RUN_CHANGED", "PLANNED_CHANGED", "PLANNED_UNCHANGED"}:
        metadata["publish_performed"] = False
        metadata["warehouse_publish_performed"] = bool(metadata.get("warehouse_publish_performed", False)) and final_status == STATUS_SUCCESS
        metadata["last_successful_updated"] = bool(metadata.get("last_successful_updated", False)) and final_status == STATUS_SUCCESS
        metadata["published_at"] = metadata["published_at"] if final_status == STATUS_SUCCESS else None

    result_payload = {
        "run_id": args.run_id,
        "run_date": args.run_date,
        "execution_mode": args.mode,
        "status": metadata["status"],
        "source_changed": metadata.get("source_changed"),
        "change_reason": metadata.get("change_reason"),
        "failed_step": metadata.get("failed_step"),
        "exception_type": metadata.get("exception_type"),
        "error_message": metadata.get("error_message"),
        "traceback_tail": metadata.get("traceback_tail"),
        "force_requested": bool(args.force),
        "force_applied": bool(metadata.get("force_applied")),
        "publish_performed": bool(publish_performed and metadata.get("status") == STATUS_SUCCESS),
        "warehouse_publish_performed": bool(metadata.get("warehouse_publish_performed")),
        "last_successful_updated": bool(metadata.get("last_successful_updated")),
        "touched_production_tables": touched_production_tables,
        "baseline": baseline_result,
        "candidate_validations": candidate_validations,
        "recovery_backups": recovery_backups or {},
        "restore_attempt": restore_attempt or {},
        "planned_actions": steps if steps else metadata.get("planned_actions", []),
        "artifacts": {
            "source_acquisition_manifest_path": str(output_dir / "source_acquisition_manifest.json"),
            "source_change_decision_path": str(output_dir / "source_change_decision.json"),
            "pipeline_run_metadata_path": str(output_dir / "pipeline_run_metadata.json"),
            "scheduled_pipeline_result_path": str(output_dir / "scheduled_pipeline_result.json"),
        },
    }

    _write_json(output_dir / "scheduled_pipeline_plan.json", result_payload)
    _write_json(output_dir / "scheduled_pipeline_result.json", result_payload)
    _write_json(output_dir / "pipeline_run_metadata.json", metadata)
    print(json.dumps({"result": result_payload, "metadata": metadata}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if metadata["status"] in {"SUCCESS", "PLANNED_UNCHANGED", "PLANNED_CHANGED", "SKIPPED_UNCHANGED", "DRY_RUN_CHANGED", BLOCKED_STATUS} else 1


def main(argv: list[str] | None = None) -> int:
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
