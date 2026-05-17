from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from config.source_registry import SourceRegistryEntry
from ops.manifest import sha256_file
from sources.connectors import (
    build_smoke_fixture,
    copy_local_file,
    download_csv_url,
    fetch_api_bytes,
    payload_to_text,
    read_local_file,
)
from sources.models import BronzeSnapshotResult
from sources.registry import compute_source_hash, decide_skip


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _payload_filename(entry: SourceRegistryEntry, payload_format: str) -> str:
    suffix = "json" if payload_format == "json" else "csv"
    return f"payload.{suffix}"


def _snapshot_dir(output_dir: str | Path, source_name: str, run_date: str) -> Path:
    return Path(output_dir).expanduser() / "bronze" / source_name / f"run_date={run_date}"


def _source_manifest_path(output_dir: str | Path) -> Path:
    return Path(output_dir).expanduser() / "source_manifest.json"


def _pipeline_manifest_path(output_dir: str | Path) -> Path:
    return Path(output_dir).expanduser() / "pipeline_manifest.json"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def materialize_source_snapshot(
    entry: SourceRegistryEntry,
    *,
    run_id: str,
    run_date: str,
    output_dir: str | Path,
    dry_run: bool,
    force: bool,
    previous_sources: dict[str, dict] | None = None,
    smoke_fixture: bool = False,
) -> BronzeSnapshotResult:
    missing_inputs = entry.missing_inputs()
    bronze_dir = _snapshot_dir(output_dir, entry.source_name, run_date)
    payload_filename = _payload_filename(entry, entry.output_format)
    payload_path = bronze_dir / payload_filename
    metadata_path = bronze_dir / "bronze_snapshot.json"

    source_hash_seed = None
    if smoke_fixture and entry.source_type in {"csv_url", "local_path", "gcs_uri"}:
        source_hash_seed = hashlib.sha256(
            build_smoke_fixture(entry).payload_bytes
        ).hexdigest()
    elif entry.source_type == "local_path" and entry.local_path:
        local_path = Path(entry.local_path).expanduser()
        if local_path.exists() and local_path.is_file():
            source_hash_seed = sha256_file(local_path)

    source_hash = compute_source_hash(entry, content_hash=source_hash_seed)
    skipped, previous = decide_skip(
        entry=entry,
        source_hash=source_hash,
        previous_sources=previous_sources or {},
        force=force,
    )

    if skipped and previous:
        return BronzeSnapshotResult(
            source_name=entry.source_name,
            source_type=entry.source_type,
            run_id=run_id,
            run_date=run_date,
            status="skipped",
            sha256=previous.get("sha256"),
            size_bytes=int(previous.get("size_bytes") or 0),
            snapshot_uri=str(previous.get("snapshot_uri") or payload_path),
            license_note=entry.license_note,
            missing_inputs=[],
            skipped=True,
            force=force,
            output_format=entry.output_format,
            source_hash=source_hash,
            input_kind=str(previous.get("input_kind") or "previous_manifest"),
            payload_path=str(payload_path),
            metadata_path=str(metadata_path),
            is_test_fixture=bool(previous.get("is_test_fixture") or False),
        )

    if missing_inputs and not smoke_fixture:
        return BronzeSnapshotResult(
            source_name=entry.source_name,
            source_type=entry.source_type,
            run_id=run_id,
            run_date=run_date,
            status="missing",
            sha256=None,
            size_bytes=0,
            snapshot_uri=str(payload_path),
            license_note=entry.license_note,
            missing_inputs=missing_inputs,
            skipped=False,
            force=force,
            output_format=entry.output_format,
            source_hash=source_hash,
            input_kind="registry",
            payload_path=str(payload_path),
            metadata_path=str(metadata_path),
            is_test_fixture=False,
        )

    payload = None
    input_kind = "registry"
    is_test_fixture = False

    if smoke_fixture and entry.source_type in {"csv_url", "local_path", "gcs_uri"}:
        payload = build_smoke_fixture(entry)
        input_kind = payload.input_kind
        is_test_fixture = payload.is_test_fixture
    elif entry.source_type == "local_path" and entry.local_path:
        payload = read_local_file(entry.local_path)
        input_kind = payload.input_kind
    elif entry.source_type == "csv_url" and entry.csv_url and not dry_run:
        payload = download_csv_url(entry.csv_url, payload_path)
        input_kind = payload.input_kind
    elif entry.source_type == "api" and entry.api_url and not dry_run:
        payload = fetch_api_bytes(entry.api_url)
        input_kind = payload.input_kind

    if payload is None:
        return BronzeSnapshotResult(
            source_name=entry.source_name,
            source_type=entry.source_type,
            run_id=run_id,
            run_date=run_date,
            status="planned" if dry_run else "missing",
            sha256=None,
            size_bytes=0,
            snapshot_uri=str(payload_path),
            license_note=entry.license_note,
            missing_inputs=missing_inputs,
            skipped=False,
            force=force,
            output_format=entry.output_format,
            source_hash=source_hash,
            input_kind="planned",
            payload_path=str(payload_path),
            metadata_path=str(metadata_path),
            is_test_fixture=False,
        )

    bronze_dir.mkdir(parents=True, exist_ok=True)
    if payload.input_kind == "local_path":
        copy_local_file(payload.source_uri, payload_path)
    else:
        payload_path.write_bytes(payload.payload_bytes)

    size_bytes = int(payload_path.stat().st_size)
    sha256 = sha256_file(payload_path)
    source_hash = compute_source_hash(entry, content_hash=sha256)
    metadata = {
        "source_name": entry.source_name,
        "source_type": entry.source_type,
        "run_id": run_id,
        "run_date": run_date,
        "generated_at": utc_now_iso(),
        "input_kind": input_kind,
        "snapshot_uri": str(payload_path),
        "payload_path": str(payload_path),
        "metadata_path": str(metadata_path),
        "size_bytes": size_bytes,
        "sha256": sha256,
        "is_test_fixture": is_test_fixture,
    }
    _write_json(metadata_path, metadata)

    return BronzeSnapshotResult(
        source_name=entry.source_name,
        source_type=entry.source_type,
        run_id=run_id,
        run_date=run_date,
        status="ingested",
        sha256=sha256,
        size_bytes=size_bytes,
        snapshot_uri=str(payload_path),
        license_note=entry.license_note,
        missing_inputs=[],
        skipped=False,
        force=force,
        output_format=entry.output_format,
        source_hash=source_hash,
        input_kind=input_kind,
        payload_path=str(payload_path),
        metadata_path=str(metadata_path),
        is_test_fixture=is_test_fixture,
    )


def build_source_manifest(
    *,
    run_id: str,
    run_date: str,
    results: list[BronzeSnapshotResult],
    dry_run: bool,
    force: bool,
    output_dir: str | Path,
    registry_path: str,
    generated_at: str | None = None,
) -> dict:
    generated = generated_at or utc_now_iso()
    source_records = [result.as_manifest_record() for result in results]
    ingested_count = sum(1 for result in results if result.status == "ingested")
    skipped_count = sum(1 for result in results if result.status == "skipped")
    missing_count = sum(1 for result in results if result.status == "missing")
    planned_count = sum(1 for result in results if result.status == "planned")
    status = "missing_inputs" if missing_count else "ok"
    if ingested_count == 0 and skipped_count == 0 and planned_count > 0 and dry_run:
        status = "planned"
    if ingested_count and (missing_count or planned_count):
        status = "partial"

    manifest = {
        "manifest_type": "source_manifest",
        "manifest_version": 1,
        "run_id": run_id,
        "run_date": run_date,
        "generated_at": generated,
        "status": status,
        "dry_run": bool(dry_run),
        "force": bool(force),
        "registry_path": registry_path,
        "output_dir": str(Path(output_dir).expanduser()),
        "source_count": len(results),
        "ingested_count": ingested_count,
        "skipped_count": skipped_count,
        "missing_count": missing_count,
        "planned_count": planned_count,
        "sources": source_records,
    }
    manifest_path = _source_manifest_path(output_dir)
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def build_pipeline_manifest(
    *,
    run_id: str,
    run_date: str,
    source_manifest: dict,
    dry_run: bool,
    force: bool,
    output_dir: str | Path,
    generated_at: str | None = None,
) -> dict:
    generated = generated_at or utc_now_iso()
    source_names = [item["source_name"] for item in source_manifest.get("sources", [])]
    status = source_manifest.get("status", "unknown")
    manifest = {
        "manifest_type": "pipeline_manifest",
        "manifest_version": 1,
        "run_id": run_id,
        "run_date": run_date,
        "generated_at": generated,
        "status": status,
        "dry_run": bool(dry_run),
        "force": bool(force),
        "output_dir": str(Path(output_dir).expanduser()),
        "source_manifest_path": source_manifest.get("manifest_path"),
        "source_count": int(source_manifest.get("source_count", 0)),
        "ingested_count": int(source_manifest.get("ingested_count", 0)),
        "skipped_count": int(source_manifest.get("skipped_count", 0)),
        "missing_count": int(source_manifest.get("missing_count", 0)),
        "planned_count": int(source_manifest.get("planned_count", 0)),
        "layout": {
            "bronze": {
                source_name: str(_snapshot_dir(output_dir, source_name, run_date))
                for source_name in source_names
            },
            "source_manifest": str(_source_manifest_path(output_dir)),
            "pipeline_manifest": str(_pipeline_manifest_path(output_dir)),
        },
        "sources": [
            {
                "source_name": item["source_name"],
                "status": item["status"],
                "source_type": item["source_type"],
                "sha256": item.get("sha256"),
                "size_bytes": item.get("size_bytes"),
                "snapshot_uri": item.get("snapshot_uri"),
                "skipped": item.get("skipped"),
                "force": item.get("force"),
            }
            for item in source_manifest.get("sources", [])
        ],
    }
    manifest["manifest_path"] = str(_pipeline_manifest_path(output_dir))
    return manifest
