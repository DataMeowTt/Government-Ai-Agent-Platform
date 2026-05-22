from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from config.source_registry import SourceRegistryEntry
from ops.manifest import sha256_file
from sources.connectors import build_smoke_fixture, download_csv_url, fetch_api_bytes
from sources.local_discovery import discover_local_source
from sources.models import BronzeSnapshotResult
from sources.registry import compute_source_hash, decide_skip


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _payload_filename(payload_format: str) -> str:
    suffix = "json" if payload_format == "json" else "csv"
    return f"payload.{suffix}"


def _snapshot_dir(output_dir: str | Path, source_name: str, run_date: str) -> Path:
    return Path(output_dir).expanduser() / "bronze" / source_name / f"run_date={run_date}"


def _source_manifest_path(output_dir: str | Path) -> Path:
    return Path(output_dir).expanduser() / "source_manifest.json"


def _pipeline_manifest_path(output_dir: str | Path) -> Path:
    return Path(output_dir).expanduser() / "pipeline_manifest.json"


def _ops_records_path(output_dir: str | Path) -> Path:
    return Path(output_dir).expanduser() / "ops_records.json"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _copy_discovered_files(
    source_discovery: dict,
    bronze_dir: Path,
) -> None:
    files_dir = bronze_dir / "files"
    for entry in source_discovery.get("files", []):
        source_path = Path(entry["absolute_path"])
        relative_path = Path(entry["relative_path"])
        destination = files_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source_path.read_bytes())


def _build_discovery_result(
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
    discovery = (
        discover_local_source(entry.source_name, entry.local_path)
        if entry.local_path
        else {
            "source_name": entry.source_name,
            "input_path": entry.local_path,
            "discovery_root": None,
            "status": "missing",
            "reason": "local_path_missing",
            "file_count": 0,
            "total_bytes": 0,
            "combined_sha256": None,
            "files": [],
            "required_files": [],
            "optional_files": [],
            "missing_required_files": [],
            "main_file": None,
            "main_file_metadata": None,
        }
    )
    source_hash = compute_source_hash(entry, content_hash=discovery.get("combined_sha256"))
    skipped, previous = decide_skip(
        entry=entry,
        source_hash=source_hash,
        previous_sources=previous_sources or {},
        force=force,
    )

    discovery_status = discovery.get("status")
    if skipped and previous:
        return BronzeSnapshotResult(
            source_name=entry.source_name,
            source_type=entry.source_type,
            run_id=run_id,
            run_date=run_date,
            status="skipped",
            discovery_status=discovery_status,
            sha256=previous.get("sha256"),
            size_bytes=int(previous.get("size_bytes") or previous.get("total_bytes") or 0),
            total_bytes=int(previous.get("total_bytes") or previous.get("size_bytes") or 0),
            file_count=int(previous.get("file_count") or 0),
            combined_sha256=previous.get("combined_sha256") or discovery.get("combined_sha256"),
            snapshot_uri=str(previous.get("snapshot_uri") or _snapshot_dir(output_dir, entry.source_name, run_date)),
            license_note=entry.license_note,
            missing_inputs=missing_inputs,
            files=list(previous.get("files") or discovery.get("files") or []),
            main_file_metadata=previous.get("main_file_metadata") or discovery.get("main_file_metadata"),
            skipped=True,
            force=force,
            output_format=entry.output_format,
            source_hash=source_hash,
            input_kind=str(previous.get("input_kind") or "previous_manifest"),
            payload_path=str(previous.get("payload_path") or (_snapshot_dir(output_dir, entry.source_name, run_date) / "bronze_snapshot.json")),
            metadata_path=str(previous.get("metadata_path") or (_snapshot_dir(output_dir, entry.source_name, run_date) / "bronze_snapshot.json")),
            is_test_fixture=bool(previous.get("is_test_fixture") or False),
            extra={
                "discovery": discovery,
                "should_run": False,
                "change_reason": "unchanged",
            },
        )

    if missing_inputs:
        return BronzeSnapshotResult(
            source_name=entry.source_name,
            source_type=entry.source_type,
            run_id=run_id,
            run_date=run_date,
            status="missing",
            discovery_status=discovery_status,
            sha256=None,
            size_bytes=0,
            total_bytes=int(discovery.get("total_bytes") or 0),
            file_count=int(discovery.get("file_count") or 0),
            combined_sha256=discovery.get("combined_sha256"),
            snapshot_uri=str(_snapshot_dir(output_dir, entry.source_name, run_date)),
            license_note=entry.license_note,
            missing_inputs=missing_inputs,
            files=list(discovery.get("files") or []),
            main_file_metadata=discovery.get("main_file_metadata"),
            skipped=False,
            force=force,
            output_format=entry.output_format,
            source_hash=source_hash,
            input_kind="registry",
            payload_path=str(_snapshot_dir(output_dir, entry.source_name, run_date) / "bronze_snapshot.json"),
            metadata_path=str(_snapshot_dir(output_dir, entry.source_name, run_date) / "bronze_snapshot.json"),
            is_test_fixture=False,
            extra={
                "discovery": discovery,
                "should_run": False,
                "change_reason": "source_input_required",
            },
        )

    if discovery_status != "present":
        return BronzeSnapshotResult(
            source_name=entry.source_name,
            source_type=entry.source_type,
            run_id=run_id,
            run_date=run_date,
            status="missing",
            discovery_status=discovery_status,
            sha256=None,
            size_bytes=0,
            total_bytes=int(discovery.get("total_bytes") or 0),
            file_count=int(discovery.get("file_count") or 0),
            combined_sha256=discovery.get("combined_sha256"),
            snapshot_uri=str(_snapshot_dir(output_dir, entry.source_name, run_date)),
            license_note=entry.license_note,
            missing_inputs=list(discovery.get("missing_required_files") or []),
            files=list(discovery.get("files") or []),
            main_file_metadata=discovery.get("main_file_metadata"),
            skipped=False,
            force=force,
            output_format=entry.output_format,
            source_hash=source_hash,
            input_kind="local_discovery",
            payload_path=str(_snapshot_dir(output_dir, entry.source_name, run_date) / "bronze_snapshot.json"),
            metadata_path=str(_snapshot_dir(output_dir, entry.source_name, run_date) / "bronze_snapshot.json"),
            is_test_fixture=False,
            extra={
                "discovery": discovery,
                "should_run": False,
                "change_reason": "invalid_source_files",
            },
        )

    bronze_dir = _snapshot_dir(output_dir, entry.source_name, run_date)
    payload_path = bronze_dir / "bronze_snapshot.json"
    materialized = False
    input_kind = "local_discovery"
    is_test_fixture = False

    if smoke_fixture and entry.source_type in {"csv_url", "local_path", "gcs_uri"}:
        payload = build_smoke_fixture(entry)
        input_kind = payload.input_kind
        is_test_fixture = payload.is_test_fixture
        bronze_dir.mkdir(parents=True, exist_ok=True)
        payload_path.write_bytes(payload.payload_bytes)
        materialized = True
    elif entry.source_type == "local_path":
        bronze_dir.mkdir(parents=True, exist_ok=True)
        _copy_discovered_files(discovery, bronze_dir)
        _write_json(
            payload_path,
            {
                "source_name": entry.source_name,
                "source_type": entry.source_type,
                "run_id": run_id,
                "run_date": run_date,
                "generated_at": utc_now_iso(),
                "input_kind": input_kind,
                "discovery_status": discovery_status,
                "source_hash": source_hash,
                "discovery": discovery,
                "license_note": entry.license_note,
            },
        )
        materialized = True
    elif entry.source_type == "csv_url" and entry.csv_url and not dry_run:
        payload = download_csv_url(entry.csv_url, payload_path)
        input_kind = payload.input_kind
        materialized = True
    elif entry.source_type == "api" and entry.api_url and not dry_run:
        payload = fetch_api_bytes(entry.api_url)
        payload_path.write_bytes(payload.payload_bytes)
        input_kind = payload.input_kind
        materialized = True

    payload_sha256 = None
    payload_size_bytes = 0
    if materialized and payload_path.exists():
        payload_sha256 = sha256_file(payload_path)
        payload_size_bytes = int(payload_path.stat().st_size)
    source_sha256 = discovery.get("combined_sha256")
    source_size_bytes = int(discovery.get("total_bytes") or 0)

    if payload_sha256 is None:
        payload_sha256 = None
    sha256 = source_sha256
    size_bytes = source_size_bytes

    if smoke_fixture and entry.source_type in {"csv_url", "local_path", "gcs_uri"}:
        sha256 = payload_sha256
        size_bytes = payload_size_bytes
    elif entry.source_type in {"csv_url", "api"} and materialized:
        sha256 = payload_sha256
        size_bytes = payload_size_bytes

    source_hash = compute_source_hash(entry, content_hash=discovery.get("combined_sha256"))
    return BronzeSnapshotResult(
        source_name=entry.source_name,
        source_type=entry.source_type,
        run_id=run_id,
        run_date=run_date,
        status="ingested" if materialized else "planned",
        discovery_status=discovery_status,
        sha256=sha256,
        size_bytes=size_bytes,
        total_bytes=source_size_bytes,
        file_count=int(discovery.get("file_count") or 0),
        combined_sha256=discovery.get("combined_sha256"),
        snapshot_uri=str(bronze_dir),
        license_note=entry.license_note,
        missing_inputs=[],
        files=list(discovery.get("files") or []),
        main_file_metadata=discovery.get("main_file_metadata"),
        skipped=False,
        force=force,
        output_format=entry.output_format,
        source_hash=source_hash,
        input_kind=input_kind,
        payload_path=str(payload_path),
        metadata_path=str(payload_path),
        is_test_fixture=is_test_fixture,
        extra={
            "discovery": discovery,
            "should_run": True,
            "change_reason": "force" if force else "new_or_changed",
            "payload_sha256": payload_sha256,
            "payload_size_bytes": payload_size_bytes,
        },
    )


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
    return _build_discovery_result(
        entry,
        run_id=run_id,
        run_date=run_date,
        output_dir=output_dir,
        dry_run=dry_run,
        force=force,
        previous_sources=previous_sources,
        smoke_fixture=smoke_fixture,
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
            "ops_records": str(_ops_records_path(output_dir)),
        },
        "sources": [
            {
                "source_name": item["source_name"],
                "status": item["status"],
                "discovery_status": item.get("discovery_status"),
                "source_type": item["source_type"],
                "sha256": item.get("sha256"),
                "size_bytes": item.get("size_bytes"),
                "total_bytes": item.get("total_bytes"),
                "file_count": item.get("file_count"),
                "combined_sha256": item.get("combined_sha256"),
                "snapshot_uri": item.get("snapshot_uri"),
                "skipped": item.get("skipped"),
                "force": item.get("force"),
            }
            for item in source_manifest.get("sources", [])
        ],
    }
    manifest["manifest_path"] = str(_pipeline_manifest_path(output_dir))
    return manifest
