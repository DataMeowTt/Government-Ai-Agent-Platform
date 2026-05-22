from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable

from ops.gcs_layout import (
    build_layout,
    pipeline_manifest_path,
    source_manifest_path,
    validate_run_date,
    validate_run_id,
    validate_source_name,
)


HASH_READ_BLOCK_SIZE = 1024 * 1024


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as file_obj:
        for read_block in iter(lambda: file_obj.read(HASH_READ_BLOCK_SIZE), b""):
            digest.update(read_block)
    return digest.hexdigest()


def combined_sha256(parts: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(str(part).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _present_file_entry(file_path: Path, input_path: Path) -> dict:
    stat = file_path.stat()
    if input_path.is_dir():
        relative_or_input_path = file_path.relative_to(input_path).as_posix()
    else:
        relative_or_input_path = str(input_path)

    return {
        "file_name": file_path.name,
        "relative_or_input_path": relative_or_input_path,
        "input_path": str(input_path),
        "absolute_path": str(file_path.resolve()),
        "sha256": sha256_file(file_path),
        "size_bytes": int(stat.st_size),
        "status": "present",
    }


def collect_source_files(source_name: str, input_path: str | Path, *, strict: bool = False) -> dict:
    source = validate_source_name(source_name)
    raw_input = str(input_path)
    if not raw_input.strip():
        raise ValueError("source input path must not be empty.")

    path = Path(raw_input).expanduser()
    if not path.exists():
        if strict:
            raise FileNotFoundError(f"Source path does not exist: {path}")
        files = [
            {
                "file_name": None,
                "relative_or_input_path": raw_input,
                "input_path": raw_input,
                "absolute_path": str(path.resolve()),
                "sha256": None,
                "size_bytes": 0,
                "status": "missing",
            }
        ]
        return {
            "source_name": source,
            "input_path": raw_input,
            "status": "missing",
            "file_count": 0,
            "total_bytes": 0,
            "combined_sha256": None,
            "files": files,
        }

    if path.is_file():
        files = [_present_file_entry(path, path)]
    elif path.is_dir():
        files = [
            _present_file_entry(file_path, path)
            for file_path in sorted(item for item in path.rglob("*") if item.is_file())
        ]
    else:
        raise ValueError(f"Source path must be a file or directory: {path}")

    total_bytes = sum(int(item["size_bytes"]) for item in files)
    hash_parts = (
        f"{item['relative_or_input_path']}:{item['sha256']}:{item['size_bytes']}"
        for item in files
    )
    return {
        "source_name": source,
        "input_path": raw_input,
        "status": "present",
        "file_count": len(files),
        "total_bytes": total_bytes,
        "combined_sha256": combined_sha256(hash_parts),
        "files": files,
    }


def build_source_manifest_payload(
    *,
    run_id: str,
    run_date: str,
    sources: dict[str, str],
    generated_at: str,
    bucket: str | None = None,
    strict: bool = False,
) -> dict:
    clean_run_id = validate_run_id(run_id)
    clean_run_date = validate_run_date(run_date)
    source_items = [
        collect_source_files(source_name, input_path, strict=strict)
        for source_name, input_path in sorted(sources.items())
    ]
    status = "present" if all(item["status"] == "present" for item in source_items) else "missing"
    return {
        "manifest_type": "source_manifest",
        "manifest_version": 1,
        "run_id": clean_run_id,
        "run_date": clean_run_date,
        "generated_at": generated_at,
        "status": status,
        "bucket": bucket,
        "manifest_path": source_manifest_path(clean_run_date, bucket),
        "source_count": len(source_items),
        "file_count": sum(int(item["file_count"]) for item in source_items),
        "total_bytes": sum(int(item["total_bytes"]) for item in source_items),
        "sources": source_items,
    }


def build_pipeline_manifest_payload(
    *,
    run_id: str,
    run_date: str,
    source_manifest: dict,
    generated_at: str,
    bucket: str | None = None,
) -> dict:
    clean_run_id = validate_run_id(run_id)
    clean_run_date = validate_run_date(run_date)
    sources = source_manifest.get("sources", [])
    source_names = [item["source_name"] for item in sources]
    return {
        "manifest_type": "pipeline_manifest",
        "manifest_version": 1,
        "run_id": clean_run_id,
        "run_date": clean_run_date,
        "generated_at": generated_at,
        "bucket": bucket,
        "manifest_path": pipeline_manifest_path(clean_run_date, bucket),
        "source_manifest_path": source_manifest.get("manifest_path"),
        "layout": build_layout(clean_run_date, source_names, bucket),
        "source_count": len(sources),
        "file_count": int(source_manifest.get("file_count", 0)),
        "total_bytes": int(source_manifest.get("total_bytes", 0)),
        "sources": [
            {
                "source_name": item["source_name"],
                "status": item["status"],
                "file_count": item["file_count"],
                "total_bytes": item["total_bytes"],
                "combined_sha256": item["combined_sha256"],
            }
            for item in sources
        ],
    }

