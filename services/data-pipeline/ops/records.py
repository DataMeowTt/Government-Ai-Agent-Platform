from __future__ import annotations

from ops.gcs_layout import (
    validate_job_name,
    validate_run_date,
    validate_run_id,
    validate_source_name,
)


def build_pipeline_run_record(
    *,
    run_id: str,
    run_date: str,
    status: str,
    source_changed: bool | None,
    raw_hashes: dict | None,
    silver_rows: int | None,
    gold_rows: dict | None,
    analytics_rows: dict | None,
    started_at: str,
    finished_at: str | None = None,
    error_message: str | None = None,
) -> dict:
    return {
        "run_id": validate_run_id(run_id),
        "run_date": validate_run_date(run_date),
        "status": str(status or "").strip(),
        "source_changed": source_changed,
        "raw_hashes": raw_hashes,
        "silver_rows": silver_rows,
        "gold_rows": gold_rows,
        "analytics_rows": analytics_rows,
        "started_at": started_at,
        "finished_at": finished_at,
        "error_message": error_message,
    }


def build_source_snapshot_record(
    *,
    run_id: str,
    run_date: str,
    source_name: str,
    status: str,
    file_count: int,
    total_bytes: int,
    combined_hash: str | None,
    manifest_path: str | None,
    recorded_at: str,
    snapshot_uri: str | None = None,
) -> dict:
    return {
        "run_id": validate_run_id(run_id),
        "run_date": validate_run_date(run_date),
        "source_name": validate_source_name(source_name),
        "status": str(status or "").strip(),
        "file_count": int(file_count),
        "total_bytes": int(total_bytes),
        "combined_hash": combined_hash,
        "manifest_path": manifest_path,
        "snapshot_uri": snapshot_uri,
        "recorded_at": recorded_at,
    }


def build_job_log_record(
    *,
    run_id: str,
    run_date: str,
    job_name: str,
    status: str,
    started_at: str,
    finished_at: str | None = None,
    error_message: str | None = None,
) -> dict:
    return {
        "run_id": validate_run_id(run_id),
        "run_date": validate_run_date(run_date),
        "job_name": validate_job_name(job_name),
        "status": str(status or "").strip(),
        "started_at": started_at,
        "finished_at": finished_at,
        "error_message": error_message,
    }


def build_ops_records(
    *,
    source_manifest: dict,
    pipeline_manifest: dict,
    started_at: str,
    finished_at: str | None = None,
    status: str | None = None,
    error_message: str | None = None,
    job_name: str = "build_manifest",
) -> dict:
    run_id = source_manifest["run_id"]
    run_date = source_manifest["run_date"]
    effective_status = status or source_manifest.get("status") or "present"
    raw_hashes = {
        item["source_name"]: item.get("sha256") or item.get("combined_sha256")
        for item in source_manifest.get("sources", [])
    }
    snapshot_records = [
        build_source_snapshot_record(
            run_id=run_id,
            run_date=run_date,
            source_name=item["source_name"],
            status=item["status"],
            file_count=int(item.get("file_count", 0)),
            total_bytes=int(item.get("size_bytes", item.get("total_bytes", 0))),
            combined_hash=item.get("sha256") or item.get("combined_sha256"),
            manifest_path=source_manifest.get("manifest_path"),
            recorded_at=finished_at or started_at,
            snapshot_uri=item.get("snapshot_uri"),
        )
        for item in source_manifest.get("sources", [])
    ]
    return {
        "pipeline_runs": [
            build_pipeline_run_record(
                run_id=run_id,
                run_date=run_date,
                status=effective_status,
                source_changed=None,
                raw_hashes=raw_hashes,
                silver_rows=None,
                gold_rows=None,
                analytics_rows=None,
                started_at=started_at,
                finished_at=finished_at,
                error_message=error_message,
            )
        ],
        "source_snapshots": snapshot_records,
        "job_logs": [
            build_job_log_record(
                run_id=run_id,
                run_date=run_date,
                job_name=job_name,
                status=effective_status,
                started_at=started_at,
                finished_at=finished_at,
                error_message=error_message,
            )
        ],
        "pipeline_manifest_path": pipeline_manifest.get("manifest_path"),
    }
