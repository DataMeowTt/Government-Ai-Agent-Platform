from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class AcquisitionError(Exception):
    message: str

    def __str__(self) -> str:
        return self.message


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(payload: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(payload)
    return digest.hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv_header_and_count(path: Path) -> tuple[list[str], int]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if header is None:
            raise AcquisitionError(f"Empty CSV file: {path}")
        row_count = 0
        for _ in reader:
            row_count += 1
    return header, row_count


def schema_signature(columns: list[str]) -> str:
    normalized = [str(col).strip().lower() for col in columns]
    payload = "|".join(normalized)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def collect_file_metadata(runtime_dir: Path, files: list[str]) -> tuple[dict[str, str], dict[str, int]]:
    hashes: dict[str, str] = {}
    sizes: dict[str, int] = {}
    for rel_name in sorted(files):
        path = runtime_dir / rel_name
        if not path.exists():
            continue
        hashes[rel_name] = sha256_file(path)
        sizes[rel_name] = int(path.stat().st_size)
    return hashes, sizes


def combined_fingerprint_payload(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_name": entry.get("source_name"),
        "upstream_dataset_code": entry.get("upstream_dataset_code"),
        "upstream_version": entry.get("upstream_version"),
        "upstream_update_date": entry.get("upstream_update_date"),
        "required_files": sorted(entry.get("required_files") or []),
        "present_files": sorted(entry.get("present_files") or []),
        "file_hashes": {k: entry.get("file_hashes", {}).get(k) for k in sorted((entry.get("file_hashes") or {}).keys())},
        "file_sizes": {k: entry.get("file_sizes", {}).get(k) for k in sorted((entry.get("file_sizes") or {}).keys())},
        "main_file_row_count": entry.get("main_file_row_count"),
        "main_file_schema_signature": entry.get("main_file_schema_signature"),
    }


def compute_combined_fingerprint(entry: dict[str, Any]) -> str:
    payload = combined_fingerprint_payload(entry)
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
