from __future__ import annotations

import argparse
import json
from pathlib import Path

from jobs.build_manifest import parse_source, utc_now_iso
from ops.change_detection import decide_source_change, load_previous_source_manifest
from ops.manifest import build_pipeline_manifest_payload, build_source_manifest_payload
from ops.ops_writer import build_ops_writer_plan
from ops.records import build_ops_records
from ops.snapshot_plan import build_gcs_upload_plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an offline GCS snapshot and gov_ai_ops dry-run plan."
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-date", required=True)
    parser.add_argument("--bucket", default=None)
    parser.add_argument("--project-id", default=None)
    parser.add_argument("--source", action="append", type=parse_source, default=[])
    parser.add_argument("--previous-manifest", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--generated-at", default=None)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--write-plan", default=None)
    return parser.parse_args()


def build_snapshot_plan(args: argparse.Namespace) -> dict:
    generated_at = args.generated_at or utc_now_iso()
    sources = dict(args.source)
    source_manifest = build_source_manifest_payload(
        run_id=args.run_id,
        run_date=args.run_date,
        sources=sources,
        generated_at=generated_at,
        bucket=args.bucket,
        strict=args.strict,
    )
    pipeline_manifest = build_pipeline_manifest_payload(
        run_id=args.run_id,
        run_date=args.run_date,
        source_manifest=source_manifest,
        generated_at=generated_at,
        bucket=args.bucket,
    )

    previous_manifest = None
    previous_missing = True
    if args.previous_manifest:
        previous_manifest, previous_missing = load_previous_source_manifest(args.previous_manifest)

    change_decision = decide_source_change(
        current_manifest=source_manifest,
        previous_manifest=previous_manifest,
        previous_manifest_missing=previous_missing,
        force=args.force,
    )
    records_status = "planned" if change_decision["should_run"] else "skipped"
    ops_records = build_ops_records(
        source_manifest=source_manifest,
        pipeline_manifest=pipeline_manifest,
        started_at=generated_at,
        finished_at=generated_at,
        status=records_status,
    )
    for row in ops_records["pipeline_runs"]:
        row["source_changed"] = change_decision["source_changed"]

    return {
        "dry_run": True,
        "run_id": args.run_id,
        "run_date": args.run_date,
        "generated_at": generated_at,
        "should_run": change_decision["should_run"],
        "source_manifest": source_manifest,
        "pipeline_manifest": pipeline_manifest,
        "change_decision": change_decision,
        "gcs_upload_plan": build_gcs_upload_plan(
            bucket=args.bucket,
            run_id=args.run_id,
            run_date=args.run_date,
            source_manifest=source_manifest,
            pipeline_manifest=pipeline_manifest,
        ),
        "ops_records": ops_records,
        "ops_writer_plan": build_ops_writer_plan(
            ops_records,
            project_id=args.project_id,
        ),
    }


def main() -> int:
    args = parse_args()
    plan = build_snapshot_plan(args)
    output = json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True)
    print(output)

    if args.write_plan:
        Path(args.write_plan).write_text(output + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
