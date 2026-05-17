from __future__ import annotations

import argparse
import json
from pathlib import Path

from config.settings import settings
from config.source_registry import source_input_required_question
from ops.records import build_ops_records
from sources.bronze import (
    build_pipeline_manifest,
    build_source_manifest,
    materialize_source_snapshot,
    utc_now_iso,
)
from sources.registry import (
    load_previous_source_manifest,
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
    parser.add_argument("--smoke-fixture", action="store_true")
    parser.add_argument("--generated-at", default=None)
    parser.add_argument("--registry-path", default=None)
    return parser.parse_args()


def build_ingest_report(args: argparse.Namespace) -> dict:
    registry = load_registry(args.registry_path)
    selected_sources = select_sources(registry, args.source)
    previous_sources = load_previous_source_manifest(args.previous_manifest)
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
    pipeline_manifest = build_pipeline_manifest(
        run_id=args.run_id,
        run_date=args.run_date,
        source_manifest=source_manifest,
        dry_run=args.dry_run,
        force=args.force,
        output_dir=output_dir,
        generated_at=generated_at,
    )

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
        "results": [result.as_manifest_record() for result in results],
        "source_manifest": source_manifest,
        "pipeline_manifest": pipeline_manifest,
        "ops_records": ops_records,
        "source_input_required_blocks": missing_blocks,
    }
    return summary


def main() -> int:
    args = parse_args()
    report = build_ingest_report(args)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
