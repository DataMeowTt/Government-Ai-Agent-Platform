from __future__ import annotations

import json
import mimetypes
import os
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

from ops.gcs_layout import (
    bronze_prefix,
    pipeline_manifest_path,
    source_manifest_path,
    validate_run_date,
    validate_run_id,
    validate_source_name,
)
from ops.manifest import sha256_file


_BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$|^[a-z0-9]$")
_BRONZE_OBJECT_CONTENT_TYPES = {
    ".csv": "text/csv",
    ".json": "application/json",
    ".txt": "text/plain",
    ".yaml": "application/x-yaml",
    ".yml": "application/x-yaml",
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def gcs_upload_runtime_dir() -> Path:
    return repo_root() / "tmp" / "gcs_upload_runtime"


def normalize_bucket(bucket: str) -> str:
    cleaned = str(bucket or "").strip()
    if cleaned.startswith("gs://"):
        cleaned = cleaned[5:]
    cleaned = cleaned.strip("/")
    if not cleaned:
        raise ValueError("gcs bucket must not be empty.")
    if "/" in cleaned or "\\" in cleaned or not _BUCKET_RE.match(cleaned):
        raise ValueError(f"Invalid gcs bucket: {bucket!r}")
    return cleaned


def cloud_write_approved() -> bool:
    return str(os.getenv("CLOUD_WRITE_APPROVED", "false")).strip().lower() == "true"


def _normalize_object_path(*parts: str) -> str:
    path = PurePosixPath()
    for part in parts:
        cleaned = str(part or "").replace("\\", "/").strip("/")
        if not cleaned:
            continue
        if cleaned == "." or cleaned.startswith("../") or "/../" in f"/{cleaned}/":
            raise ValueError(f"Unsafe GCS object path segment: {part!r}")
        path = path / cleaned
    object_path = path.as_posix()
    if object_path.startswith("../") or "/../" in f"/{object_path}/":
        raise ValueError(f"Unsafe GCS object path: {object_path!r}")
    return object_path


def build_gcs_uri(bucket: str, *parts: str) -> str:
    clean_bucket = normalize_bucket(bucket)
    object_path = _normalize_object_path(*parts)
    if not object_path:
        raise ValueError("GCS object path must not be empty.")
    return f"gs://{clean_bucket}/{object_path}"


def _content_type_for_path(path: Path) -> str | None:
    if path.suffix.lower() in _BRONZE_OBJECT_CONTENT_TYPES:
        return _BRONZE_OBJECT_CONTENT_TYPES[path.suffix.lower()]
    content_type, _ = mimetypes.guess_type(path.name)
    return content_type


def _plan_entry(
    *,
    artifact_type: str,
    source_name: str,
    local_path: Path,
    target_gcs_uri: str,
    status: str,
    source_relative_path: str | None = None,
) -> dict[str, Any]:
    stat = local_path.stat() if local_path.exists() else None
    return {
        "artifact_type": artifact_type,
        "source_name": source_name,
        "source_relative_path": source_relative_path,
        "local_path": str(local_path),
        "target_gcs_uri": target_gcs_uri,
        "bytes": int(stat.st_size) if stat else 0,
        "sha256": sha256_file(local_path) if stat else None,
        "content_type": _content_type_for_path(local_path),
        "status": status,
    }


def _manifest_entry(
    *,
    artifact_type: str,
    source_name: str,
    local_path: Path,
    target_gcs_uri: str,
    status: str,
) -> dict[str, Any]:
    return _plan_entry(
        artifact_type=artifact_type,
        source_name=source_name,
        local_path=local_path,
        target_gcs_uri=target_gcs_uri,
        status=status,
    )


def _bronze_entries(
    *,
    output_dir: Path,
    bucket: str,
    run_date: str,
) -> list[dict[str, Any]]:
    bronze_root = output_dir / "bronze"
    if not bronze_root.exists():
        return []

    entries: list[dict[str, Any]] = []
    for file_path in sorted(item for item in bronze_root.rglob("*") if item.is_file()):
        relative_path = file_path.relative_to(output_dir).as_posix()
        parts = relative_path.split("/")
        if len(parts) < 4 or parts[0] != "bronze" or parts[2] != f"run_date={run_date}":
            raise ValueError(f"Unexpected bronze path layout: {relative_path!r}")
        source_name = validate_source_name(parts[1])
        target_uri = build_gcs_uri(bucket, relative_path)
        entries.append(
            _plan_entry(
                artifact_type="bronze_file",
                source_name=source_name,
                local_path=file_path,
                target_gcs_uri=target_uri,
                status="planned",
                source_relative_path="/".join(parts[3:]),
            )
        )
    return entries


def _manifest_entries(
    *,
    output_dir: Path,
    bucket: str,
    run_date: str,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []

    source_manifest = output_dir / "source_manifest.json"
    pipeline_manifest = output_dir / "pipeline_manifest.json"
    ops_records = output_dir / "ops_records.json"

    entries.append(
        _manifest_entry(
            artifact_type="source_manifest",
            source_name="source_manifest",
            local_path=source_manifest,
            target_gcs_uri=source_manifest_path(run_date, bucket),
            status="planned" if source_manifest.exists() else "missing",
        )
    )
    entries.append(
        _manifest_entry(
            artifact_type="pipeline_manifest",
            source_name="pipeline_manifest",
            local_path=pipeline_manifest,
            target_gcs_uri=pipeline_manifest_path(run_date, bucket),
            status="planned" if pipeline_manifest.exists() else "missing",
        )
    )
    if ops_records.exists():
        entries.append(
            _manifest_entry(
                artifact_type="ops_records",
                source_name="ops_records",
                local_path=ops_records,
                target_gcs_uri=build_gcs_uri(
                    bucket,
                    "manifests",
                    "ops_records",
                    f"run_date={validate_run_date(run_date)}",
                    "ops_records.json",
                ),
                status="planned",
            )
        )

    return entries


def build_upload_plan(
    *,
    output_dir: str | Path,
    bucket: str,
    run_id: str,
    run_date: str,
    dry_run: bool,
    cloud_approved: bool | None = None,
) -> dict[str, Any]:
    clean_run_id = validate_run_id(run_id)
    clean_run_date = validate_run_date(run_date)
    clean_bucket = normalize_bucket(bucket)
    output_path = Path(output_dir).expanduser().resolve()
    plan_entries = _bronze_entries(
        output_dir=output_path,
        bucket=clean_bucket,
        run_date=clean_run_date,
    )
    plan_entries.extend(
        _manifest_entries(
            output_dir=output_path,
            bucket=clean_bucket,
            run_date=clean_run_date,
        )
    )
    plan_entries = sorted(plan_entries, key=lambda item: item["target_gcs_uri"])

    upload_mode = "dry_run" if dry_run or not (cloud_approved if cloud_approved is not None else cloud_write_approved()) else "upload"
    plan_status = "planned"
    source_names = sorted(
        {
            entry["source_name"]
            for entry in plan_entries
            if entry["artifact_type"] == "bronze_file" and entry["status"] != "missing"
        }
    )
    target_prefixes = sorted(
        {
            entry["target_gcs_uri"].rsplit("/", 1)[0] + "/"
            for entry in plan_entries
            if entry["status"] != "missing"
        }
    )
    total_bytes = sum(int(entry["bytes"] or 0) for entry in plan_entries if entry["status"] != "missing")
    object_count = sum(1 for entry in plan_entries if entry["status"] != "missing")

    return {
        "run_id": clean_run_id,
        "run_date": clean_run_date,
        "gcs_bucket": clean_bucket,
        "mode": upload_mode,
        "status": plan_status,
        "cloud_write_approved": bool(cloud_approved if cloud_approved is not None else cloud_write_approved()),
        "object_count": object_count,
        "total_bytes": total_bytes,
        "source_names": source_names,
        "target_prefixes": target_prefixes,
        "source_manifest_path": source_manifest_path(clean_run_date, clean_bucket),
        "pipeline_manifest_path": pipeline_manifest_path(clean_run_date, clean_bucket),
        "ops_records_path": build_gcs_uri(
            clean_bucket,
            "manifests",
            "ops_records",
            f"run_date={clean_run_date}",
            "ops_records.json",
        ),
        "objects": plan_entries,
    }


def enrich_manifests_for_upload(
    *,
    source_manifest: dict[str, Any],
    pipeline_manifest: dict[str, Any],
    upload_plan: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    bronze_targets = {
        item["source_name"]: item["target_gcs_uri"]
        for item in upload_plan.get("objects", [])
        if item.get("artifact_type") == "bronze_file" and item.get("status") != "missing"
    }
    target_prefixes = upload_plan.get("target_prefixes", [])

    source_manifest["gcs_bucket"] = upload_plan.get("gcs_bucket")
    source_manifest["upload_mode"] = upload_plan.get("mode")
    source_manifest["upload_plan_path"] = str(gcs_upload_runtime_dir() / "upload_plan.json")
    source_manifest["gcs_target_prefixes"] = list(target_prefixes)
    source_manifest["sources"] = [
        {
            **item,
            "target_gcs_uri": bronze_targets.get(item["source_name"]),
        }
        if item.get("source_name") in bronze_targets
        else item
        for item in source_manifest.get("sources", [])
    ]

    pipeline_manifest["gcs_bucket"] = upload_plan.get("gcs_bucket")
    pipeline_manifest["upload_mode"] = upload_plan.get("mode")
    pipeline_manifest["upload_plan_path"] = str(gcs_upload_runtime_dir() / "upload_plan.json")
    pipeline_manifest["object_count"] = int(upload_plan.get("object_count", 0))
    pipeline_manifest["total_bytes"] = int(upload_plan.get("total_bytes", 0))
    pipeline_manifest["target_prefixes"] = list(target_prefixes)
    pipeline_manifest["source_manifest_target_uri"] = upload_plan.get("source_manifest_path")
    pipeline_manifest["pipeline_manifest_target_uri"] = upload_plan.get("pipeline_manifest_path")
    pipeline_manifest["ops_records_target_uri"] = upload_plan.get("ops_records_path")
    return source_manifest, pipeline_manifest


def summarize_upload_plan(upload_plan: dict[str, Any]) -> dict[str, Any]:
    objects = list(upload_plan.get("objects", []))
    planned = sum(1 for item in objects if item.get("status") == "planned")
    blocked = sum(1 for item in objects if item.get("status") == "blocked")
    skipped = sum(1 for item in objects if item.get("status") == "skipped")
    uploaded = sum(1 for item in objects if item.get("status") == "uploaded")
    missing = sum(1 for item in objects if item.get("status") == "missing")
    return {
        "run_id": upload_plan.get("run_id"),
        "run_date": upload_plan.get("run_date"),
        "gcs_bucket": upload_plan.get("gcs_bucket"),
        "mode": upload_plan.get("mode"),
        "status": upload_plan.get("status"),
        "object_count": int(upload_plan.get("object_count", 0)),
        "total_bytes": int(upload_plan.get("total_bytes", 0)),
        "source_names": list(upload_plan.get("source_names", [])),
        "target_prefixes": list(upload_plan.get("target_prefixes", [])),
        "planned_count": planned,
        "blocked_count": blocked,
        "skipped_count": skipped,
        "uploaded_count": uploaded,
        "missing_count": missing,
        "objects": objects,
    }


def write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    output = Path(path).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output


def preflight_gcloud(bucket: str) -> dict[str, str]:
    clean_bucket = normalize_bucket(bucket)
    project = subprocess.run(
        ["gcloud", "config", "get-value", "project"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    active_account = subprocess.run(
        ["gcloud", "auth", "list", "--filter=status:ACTIVE", "--format=value(account)"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    bucket_desc = subprocess.run(
        ["gcloud", "storage", "buckets", "describe", f"gs://{clean_bucket}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return {
        "project": project,
        "active_account": active_account,
        "bucket_description": bucket_desc,
    }


def execute_upload_plan(upload_plan: dict[str, Any]) -> dict[str, Any]:
    if not upload_plan.get("cloud_write_approved"):
        return {
            "status": "blocked",
            "reason": "cloud_write_approved_false",
            "gcs_bucket": upload_plan.get("gcs_bucket"),
            "run_id": upload_plan.get("run_id"),
            "run_date": upload_plan.get("run_date"),
            "uploaded_count": 0,
        }

    preflight = preflight_gcloud(str(upload_plan["gcs_bucket"]))
    uploaded: list[dict[str, Any]] = []
    for entry in upload_plan.get("objects", []):
        if entry.get("status") == "missing":
            uploaded.append({**entry, "status": "skipped"})
            continue
        subprocess.run(
            ["gcloud", "storage", "cp", entry["local_path"], entry["target_gcs_uri"]],
            check=True,
        )
        uploaded.append({**entry, "status": "uploaded"})

    verify_results: list[dict[str, Any]] = []
    for prefix in upload_plan.get("target_prefixes", []):
        result = subprocess.run(
            ["gcloud", "storage", "ls", "-l", f"{prefix}**"],
            capture_output=True,
            text=True,
            check=True,
        )
        verify_results.append(
            {
                "prefix": prefix,
                "output": result.stdout.strip(),
            }
        )

    return {
        "status": "uploaded",
        "run_id": upload_plan.get("run_id"),
        "run_date": upload_plan.get("run_date"),
        "gcs_bucket": upload_plan.get("gcs_bucket"),
        "preflight": preflight,
        "uploaded_count": sum(1 for item in uploaded if item["status"] == "uploaded"),
        "skipped_count": sum(1 for item in uploaded if item["status"] == "skipped"),
        "verify_results": verify_results,
        "objects": uploaded,
    }
