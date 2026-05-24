from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

from config.settings import settings
from ops.source_fingerprint import decide_source_change
from sources.faostat_macro import materialize_fao_macro
from sources.global_macro_database import materialize_gmd
from sources.official_acquisition import AcquisitionError, utc_now_iso
from sources.world_bank_wdi import materialize_wdi


VALID_SOURCES = ("wdi", "fao_macro", "gmd")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch official source candidates for local/dry-run ETL compatibility checks.")
    parser.add_argument("--mode", choices=["plan", "dry_run"], default="plan")
    parser.add_argument("--source", action="append", default=None, choices=["wdi", "fao_macro", "gmd", "all"])
    parser.add_argument("--run-id", default=settings.run_id)
    parser.add_argument("--run-date", default=settings.run_date)
    parser.add_argument("--runtime-raw-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--last-successful-manifest", default=None)
    parser.add_argument("--allow-network", action="store_true")
    return parser.parse_args()


def _selected_sources(raw_sources: list[str] | None) -> list[str]:
    if not raw_sources or "all" in raw_sources:
        return list(VALID_SOURCES)
    seen: list[str] = []
    for source in raw_sources:
        if source not in seen:
            seen.append(source)
    return seen


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_plan_manifest(args: argparse.Namespace, selected_sources: list[str]) -> dict:
    return {
        "run_id": args.run_id,
        "run_date": args.run_date,
        "mode": args.mode,
        "status": "planned",
        "acquired_at": utc_now_iso(),
        "selected_sources": selected_sources,
        "sources": [],
        "fingerprint_version": "v1",
        "provenance_policy": "official_source_only_no_html_scrape",
        "license_notes": [
            "WDI official references: https://wdi.worldbank.org/",
            "FAOSTAT official catalog: https://bulks-faostat.fao.org/production/datasets_E.json",
            "GMD is non-commercial citation-required dataset (CC BY-NC-SA 4.0).",
        ],
    }


def run_acquisition(
    *,
    args: argparse.Namespace,
    selected_sources: list[str],
    wdi_fn: Callable[..., dict] = materialize_wdi,
    fao_fn: Callable[..., dict] = materialize_fao_macro,
    gmd_fn: Callable[..., dict] = materialize_gmd,
) -> tuple[dict, list[dict]]:
    manifest = build_plan_manifest(args, selected_sources)
    manifest["status"] = "valid"
    runtime_raw_dir = Path(args.runtime_raw_dir).expanduser()
    runtime_raw_dir.mkdir(parents=True, exist_ok=True)

    errors: list[dict] = []
    for source_name in selected_sources:
        try:
            if source_name == "wdi":
                entry = wdi_fn(runtime_raw_dir=runtime_raw_dir, allow_network=args.allow_network)
            elif source_name == "fao_macro":
                entry = fao_fn(runtime_raw_dir=runtime_raw_dir, allow_network=args.allow_network)
            else:
                entry = gmd_fn(runtime_raw_dir=runtime_raw_dir, allow_network=args.allow_network)
            manifest["sources"].append(entry)
        except AcquisitionError as exc:
            manifest["status"] = "acquisition_failed"
            errors.append({"source_name": source_name, "error": str(exc)})
            manifest["sources"].append(
                {
                    "source_name": source_name,
                    "validation_status": "invalid",
                    "error_message": str(exc),
                    "required_files": [],
                    "present_files": [],
                    "missing_files": [],
                }
            )

    return manifest, errors


def main() -> int:
    args = parse_args()
    selected = _selected_sources(args.source)
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.mode == "plan":
        manifest = build_plan_manifest(args, selected)
        decision = decide_source_change(mode="plan", candidate_manifest=manifest, baseline_path=args.last_successful_manifest)
        _write_json(output_dir / "source_acquisition_manifest.json", manifest)
        _write_json(output_dir / "source_change_decision.json", decision)
        print(json.dumps({"manifest": manifest, "decision": decision}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    manifest, errors = run_acquisition(args=args, selected_sources=selected)
    decision = decide_source_change(mode="dry_run", candidate_manifest=manifest, baseline_path=args.last_successful_manifest)

    _write_json(output_dir / "source_acquisition_manifest.json", manifest)
    _write_json(output_dir / "source_change_decision.json", decision)
    if errors:
        _write_json(output_dir / "source_acquisition_errors.json", {"errors": errors})

    print(json.dumps({"manifest": manifest, "decision": decision, "errors": errors}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
