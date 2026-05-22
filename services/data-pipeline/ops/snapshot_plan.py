from __future__ import annotations

from pathlib import Path

from ops.gcs_layout import (
    analytics_prefix,
    bronze_prefix,
    data_quality_report_path,
    gold_prefix,
    pipeline_manifest_path,
    silver_prefix,
    source_manifest_path,
    validate_run_date,
    validate_run_id,
    validate_source_name,
)
from ops.manifest import sha256_file


def _join_object(prefix: str, object_name: str) -> str:
    clean_name = str(object_name or "").strip().replace("\\", "/").lstrip("/")
    if not clean_name:
        raise ValueError("object name must not be empty.")
    return f"{prefix.rstrip('/')}/{clean_name}"


def _raw_object_name(source: dict, file_entry: dict) -> str:
    relative_path = str(file_entry.get("relative_or_input_path") or "").replace("\\", "/")
    input_path = str(source.get("input_path") or "").replace("\\", "/")
    file_name = file_entry.get("file_name")

    if file_name and relative_path == input_path:
        return str(file_name)

    if file_name and not relative_path:
        return str(file_name)

    if relative_path:
        if ":" in relative_path or relative_path.startswith("/"):
            return str(file_name or Path(relative_path).name)
        return relative_path

    return str(file_name or "missing")


def _entry(
    *,
    artifact_type: str,
    destination_uri: str,
    source_path: str | None = None,
    source_id: str | None = None,
    size_bytes: int | None = None,
    sha256: str | None = None,
    status: str = "planned",
) -> dict:
    return {
        "artifact_type": artifact_type,
        "source_path": source_path,
        "source_id": source_id,
        "destination_uri": destination_uri,
        "size_bytes": size_bytes,
        "sha256": sha256,
        "status": status,
        "dry_run": True,
    }


def _local_artifact_entry(
    *,
    artifact_type: str,
    path: str,
    destination_uri: str,
) -> dict:
    source_path = str(path)
    local_path = Path(source_path).expanduser()
    if not local_path.exists() or not local_path.is_file():
        return _entry(
            artifact_type=artifact_type,
            source_path=source_path,
            destination_uri=destination_uri,
            status="missing",
        )

    return _entry(
        artifact_type=artifact_type,
        source_path=source_path,
        destination_uri=destination_uri,
        size_bytes=int(local_path.stat().st_size),
        sha256=sha256_file(local_path),
    )


def check_duplicate_destinations(entries: list[dict]) -> None:
    seen: dict[str, int] = {}
    duplicates: list[str] = []
    for entry in entries:
        destination = entry["destination_uri"]
        seen[destination] = seen.get(destination, 0) + 1
        if seen[destination] == 2:
            duplicates.append(destination)

    if duplicates:
        raise ValueError(f"Duplicate destination_uri values in upload plan: {duplicates}")


def build_gcs_upload_plan(
    *,
    bucket: str | None,
    run_id: str,
    run_date: str,
    source_manifest: dict,
    pipeline_manifest: dict,
    silver_paths: list[str] | tuple[str, ...] | None = None,
    gold_paths: list[str] | tuple[str, ...] | None = None,
    analytics_paths: list[str] | tuple[str, ...] | None = None,
    report_paths: list[str] | tuple[str, ...] | None = None,
) -> list[dict]:
    validate_run_id(run_id)
    clean_run_date = validate_run_date(run_date)

    entries: list[dict] = []
    for source in sorted(source_manifest.get("sources", []), key=lambda item: item["source_name"]):
        source_name = validate_source_name(source["source_name"])
        prefix = bronze_prefix(source_name, clean_run_date, bucket)
        files = sorted(
            source.get("files", []),
            key=lambda item: str(item.get("relative_or_input_path") or ""),
        )
        for file_entry in files:
            object_name = _raw_object_name(source, file_entry)
            destination_uri = _join_object(prefix, object_name)
            status = "planned" if file_entry.get("status") == "present" else "missing"
            entries.append(
                _entry(
                    artifact_type="raw_source",
                    source_path=file_entry.get("absolute_path") or file_entry.get("input_path"),
                    source_id=f"{source_name}:{object_name}",
                    destination_uri=destination_uri,
                    size_bytes=file_entry.get("size_bytes"),
                    sha256=file_entry.get("sha256"),
                    status=status,
                )
            )

    entries.append(
        _entry(
            artifact_type="source_manifest",
            source_id=source_manifest.get("manifest_type"),
            destination_uri=source_manifest_path(clean_run_date, bucket),
        )
    )
    entries.append(
        _entry(
            artifact_type="pipeline_manifest",
            source_id=pipeline_manifest.get("manifest_type"),
            destination_uri=pipeline_manifest_path(clean_run_date, bucket),
        )
    )

    for path in sorted(silver_paths or []):
        entries.append(
            _local_artifact_entry(
                artifact_type="silver",
                path=path,
                destination_uri=_join_object(silver_prefix(clean_run_date, bucket), Path(path).name),
            )
        )

    for path in sorted(gold_paths or []):
        entries.append(
            _local_artifact_entry(
                artifact_type="gold",
                path=path,
                destination_uri=_join_object(gold_prefix(clean_run_date, bucket), Path(path).name),
            )
        )

    for path in sorted(analytics_paths or []):
        entries.append(
            _local_artifact_entry(
                artifact_type="analytics",
                path=path,
                destination_uri=_join_object(analytics_prefix(clean_run_date, bucket), Path(path).name),
            )
        )

    for path in sorted(report_paths or []):
        destination = data_quality_report_path(clean_run_date, bucket)
        entries.append(
            _local_artifact_entry(
                artifact_type="report",
                path=path,
                destination_uri=destination,
            )
        )

    check_duplicate_destinations(entries)
    return entries

