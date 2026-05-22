from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from ops.manifest import build_pipeline_manifest_payload, build_source_manifest_payload
from ops.records import build_ops_records


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_source(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("--source must use NAME=PATH format.")
    name, path = value.split("=", 1)
    if not name.strip() or not path.strip():
        raise argparse.ArgumentTypeError("--source requires non-empty NAME and PATH.")
    return name.strip(), path.strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build deterministic local source and pipeline manifest payloads."
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-date", required=True)
    parser.add_argument("--source", action="append", type=parse_source, default=[])
    parser.add_argument("--bucket", default=None)
    parser.add_argument("--generated-at", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--write", action="store_true")
    return parser.parse_args()


def build_payload(args: argparse.Namespace) -> dict:
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
    ops_records = build_ops_records(
        source_manifest=source_manifest,
        pipeline_manifest=pipeline_manifest,
        started_at=generated_at,
        finished_at=generated_at,
    )
    return {
        "source_manifest": source_manifest,
        "pipeline_manifest": pipeline_manifest,
        "ops_records": ops_records,
    }


def write_payloads(payload: dict, output_dir: str) -> None:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    for name, content in (
        ("source_manifest.json", payload["source_manifest"]),
        ("pipeline_manifest.json", payload["pipeline_manifest"]),
        ("ops_records.json", payload["ops_records"]),
    ):
        (target / name).write_text(
            json.dumps(content, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def main() -> int:
    args = parse_args()
    if args.write and not args.output_dir:
        raise SystemExit("--write requires --output-dir.")

    payload = build_payload(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))

    if args.write:
        write_payloads(payload, args.output_dir)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
