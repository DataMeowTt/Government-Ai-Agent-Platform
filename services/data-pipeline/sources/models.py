from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BronzeSnapshotResult:
    source_name: str
    source_type: str
    run_id: str
    run_date: str
    status: str
    discovery_status: str | None
    sha256: str | None
    size_bytes: int
    total_bytes: int
    file_count: int
    combined_sha256: str | None
    snapshot_uri: str
    license_note: str | None
    missing_inputs: list[str]
    files: list[dict[str, Any]]
    main_file_metadata: dict[str, Any] | None
    skipped: bool
    force: bool
    output_format: str
    source_hash: str | None
    input_kind: str
    payload_path: str | None = None
    metadata_path: str | None = None
    is_test_fixture: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def as_manifest_record(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "source_type": self.source_type,
            "run_id": self.run_id,
            "run_date": self.run_date,
            "status": self.status,
            "discovery_status": self.discovery_status,
            "sha256": self.sha256,
            "size_bytes": int(self.size_bytes),
            "total_bytes": int(self.total_bytes),
            "file_count": int(self.file_count),
            "combined_sha256": self.combined_sha256,
            "snapshot_uri": self.snapshot_uri,
            "license_note": self.license_note,
            "missing_inputs": list(self.missing_inputs),
            "files": list(self.files),
            "main_file_metadata": self.main_file_metadata,
            "skipped": bool(self.skipped),
            "force": bool(self.force),
            "output_format": self.output_format,
            "source_hash": self.source_hash,
            "input_kind": self.input_kind,
            "payload_path": self.payload_path,
            "metadata_path": self.metadata_path,
            "is_test_fixture": bool(self.is_test_fixture),
            **self.extra,
        }


@dataclass(frozen=True)
class SourceSelection:
    source_names: list[str]
    requested_all: bool = False


@dataclass(frozen=True)
class IngestRunSummary:
    run_id: str
    run_date: str
    dry_run: bool
    force: bool
    output_dir: str
    source_manifest_path: str
    pipeline_manifest_path: str
    source_count: int
    ingested_count: int
    skipped_count: int
    missing_count: int
    planned_count: int
    source_input_required_blocks: list[str]
    source_manifest: dict[str, Any]
    pipeline_manifest: dict[str, Any]
    results: list[dict[str, Any]]
