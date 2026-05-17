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
    sha256: str | None
    size_bytes: int
    snapshot_uri: str
    license_note: str | None
    missing_inputs: list[str]
    skipped: bool
    force: bool
    output_format: str
    source_hash: str | None
    input_kind: str
    payload_path: str | None = None
    metadata_path: str | None = None
    is_test_fixture: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def file_count(self) -> int:
        return 1 if self.status in {"ingested", "skipped", "planned"} and self.size_bytes > 0 else 0

    def as_manifest_record(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "source_type": self.source_type,
            "run_id": self.run_id,
            "run_date": self.run_date,
            "status": self.status,
            "sha256": self.sha256,
            "size_bytes": int(self.size_bytes),
            "snapshot_uri": self.snapshot_uri,
            "license_note": self.license_note,
            "missing_inputs": list(self.missing_inputs),
            "skipped": bool(self.skipped),
            "force": bool(self.force),
            "output_format": self.output_format,
            "source_hash": self.source_hash,
            "input_kind": self.input_kind,
            "file_count": self.file_count,
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
