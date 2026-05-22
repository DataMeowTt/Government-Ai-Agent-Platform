from __future__ import annotations

import argparse
import json
from pathlib import Path

from config.settings import settings
from config.source_registry import source_input_required_question
from ops.change_detection import (
    decide_source_change,
    load_previous_source_manifest as load_previous_source_manifest_payload,
)
from ops.records import build_ops_records
from sources.bronze import (
    build_pipeline_manifest,
    build_source_manifest,
    materialize_source_snapshot,
    utc_now_iso,
)
from sources.gcs_upload import (
    build_upload_plan,
    cloud_write_approved,
    enrich_manifests_for_upload,
    execute_upload_plan,
    gcs_upload_runtime_dir,
    summarize_upload_plan,
    write_json as write_json_file,
)
from sources.registry import (
    load_previous_source_manifest as load_previous_source_manifest_sources,
    load_registry,
    select_sources,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest configured sources into local bronze snapshots and manifests."
    )
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="Source name to ingest. Use --source all to select all enabled sources.",
    )
    parser.add_argument("--run-id", default=settings.run_id)
    parser.add_argument("--run-date", default=settings.run_date)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--previous-manifest", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", default=True)
    parser.add_argument("--no-dry-run", dest="dry_run", action="store_false")
    parser.add_argument("--upload-gcs", action="store_true")
    parser.add_argument("--gcs-bucket", default=None)
    parser.add_argument("--smoke-fixture", action="store_true")
    parser.add_argument("--generated-at", default=None)
    parser.add_argument("--registry-path", default=None)
    return parser.parse_args()


def build_ingest_report(args: argparse.Namespace) -> dict:
    registry = load_registry(args.registry_path)
    selected_sources = select_sources(registry, args.source)
    previous_sources = load_previous_source_manifest_sources(args.previous_manifest)
    if args.previous_manifest:
        previous_manifest, previous_missing = load_previous_source_manifest_payload(args.previous_manifest)
    else:
        previous_manifest, previous_missing = None, True
    generated_at = args.generated_at or utc_now_iso()
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    results = [
        materialize_source_snapshot(
            entry,
            run_id=args.run_id,
            run_date=args.run_date,
            output_dir=output_dir,
            dry_run=args.dry_run,
            force=args.force,
            previous_sources=previous_sources,
            smoke_fixture=args.smoke_fixture,
        )
        for entry in selected_sources
    ]

    source_manifest = build_source_manifest(
        run_id=args.run_id,
        run_date=args.run_date,
        results=results,
        dry_run=args.dry_run,
        force=args.force,
        output_dir=output_dir,
        registry_path=args.registry_path or settings.source_registry_path,
        generated_at=generated_at,
    )

    change_decision = decide_source_change(
        current_manifest=source_manifest,
        previous_manifest=previous_manifest,
        previous_manifest_missing=previous_missing,
        force=args.force,
    )
    source_manifest["should_run"] = bool(change_decision["should_run"])
    source_manifest["change_reason"] = change_decision["reason"]
    source_manifest["source_changed"] = bool(change_decision["source_changed"])
    pipeline_manifest = build_pipeline_manifest(
        run_id=args.run_id,
        run_date=args.run_date,
        source_manifest=source_manifest,
        dry_run=args.dry_run,
        force=args.force,
        output_dir=output_dir,
        generated_at=generated_at,
    )
    pipeline_manifest["should_run"] = bool(change_decision["should_run"])
    pipeline_manifest["change_reason"] = change_decision["reason"]
    pipeline_manifest["source_changed"] = bool(change_decision["source_changed"])

    source_manifest_path = output_dir / "source_manifest.json"
    pipeline_manifest_path = output_dir / "pipeline_manifest.json"
    source_manifest_path.write_text(
        json.dumps(source_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    pipeline_manifest_path.write_text(
        json.dumps(pipeline_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ops_records = build_ops_records(
        source_manifest=source_manifest,
        pipeline_manifest=pipeline_manifest,
        started_at=generated_at,
        finished_at=generated_at,
        status="planned" if args.dry_run else "completed",
        job_name="ingest_sources",
    )
    ops_records_path = output_dir / "ops_records.json"
    ops_records_path.write_text(
        json.dumps(ops_records, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    missing_blocks: list[str] = []
    for result in results:
        if result.status != "missing":
            continue
        for missing_field in result.missing_inputs:
            missing_blocks.append(
                "\n".join(
                    [
                        "SOURCE INPUT REQUIRED:",
                        f"- source_name: {result.source_name}",
                        f"- missing field: {missing_field}",
                        f"- exact question for user: {source_input_required_question(result.source_name, missing_field)}",
                    ]
                )
            )

    summary = {
        "run_id": args.run_id,
        "run_date": args.run_date,
        "dry_run": bool(args.dry_run),
        "force": bool(args.force),
        "source_count": len(results),
        "ingested_count": sum(1 for item in results if item.status == "ingested"),
        "skipped_count": sum(1 for item in results if item.status == "skipped"),
        "missing_count": sum(1 for item in results if item.status == "missing"),
        "planned_count": sum(1 for item in results if item.status == "planned"),
        "source_manifest_path": str(source_manifest_path),
        "pipeline_manifest_path": str(pipeline_manifest_path),
        "output_dir": str(output_dir),
        "should_run": bool(change_decision["should_run"]),
        "change_reason": change_decision["reason"],
        "results": [result.as_manifest_record() for result in results],
        "source_manifest": source_manifest,
        "pipeline_manifest": pipeline_manifest,
        "ops_records": ops_records,
        "ops_records_path": str(ops_records_path),
        "source_input_required_blocks": missing_blocks,
    }
    return summary


def _persist_upload_artifacts(
    *,
    report: dict,
    args: argparse.Namespace,
) -> dict:
    if not args.upload_gcs:
        return {}

    if not args.gcs_bucket:
        raise ValueError("--gcs-bucket is required when --upload-gcs is set.")

    approved = cloud_write_approved()
    output_dir = Path(report["output_dir"]).expanduser()
    upload_plan = build_upload_plan(
        output_dir=output_dir,
        bucket=args.gcs_bucket,
        run_id=args.run_id,
        run_date=args.run_date,
        dry_run=args.dry_run,
        cloud_approved=approved,
    )
    runtime_dir = gcs_upload_runtime_dir()
    upload_plan_path = runtime_dir / "upload_plan.json"
    write_json_file(upload_plan_path, upload_plan)

    source_manifest = report["source_manifest"]
    pipeline_manifest = report["pipeline_manifest"]
    enrich_manifests_for_upload(
        source_manifest=source_manifest,
        pipeline_manifest=pipeline_manifest,
        upload_plan=upload_plan,
    )
    write_json_file(Path(report["source_manifest_path"]), source_manifest)
    write_json_file(Path(report["pipeline_manifest_path"]), pipeline_manifest)

    summary = summarize_upload_plan(upload_plan)
    summary["upload_plan_path"] = str(upload_plan_path)
    summary["cloud_write_approved"] = approved

    if approved and not args.dry_run:
        upload_result = execute_upload_plan(upload_plan)
        upload_result_path = runtime_dir / "upload_result.json"
        write_json_file(upload_result_path, upload_result)
        summary["upload_result_path"] = str(upload_result_path)
        summary["upload_result"] = upload_result
        pipeline_manifest["upload_mode"] = upload_result.get("status", pipeline_manifest.get("upload_mode"))
        pipeline_manifest["uploaded_object_count"] = int(upload_result.get("uploaded_count", 0))
        pipeline_manifest["upload_verification"] = {
            "status": upload_result.get("status"),
            "preflight": upload_result.get("preflight"),
            "verify_results": upload_result.get("verify_results", []),
        }
        source_manifest["upload_mode"] = "upload"
        write_json_file(Path(report["source_manifest_path"]), source_manifest)
        write_json_file(Path(report["pipeline_manifest_path"]), pipeline_manifest)
    else:
        summary["status"] = "blocked" if not approved and not args.dry_run else summary.get("status")

    report["source_manifest"] = source_manifest
    report["pipeline_manifest"] = pipeline_manifest
    report["upload_gcs"] = summary
    return summary


def main() -> int:
    args = parse_args()
    report = build_ingest_report(args)
    if args.upload_gcs:
        _persist_upload_artifacts(report=report, args=args)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    has_required_input_error = any(result["status"] == "missing" for result in report["results"])
    if has_required_input_error and not args.dry_run:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
