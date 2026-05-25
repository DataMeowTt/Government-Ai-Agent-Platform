from __future__ import annotations

import re
from datetime import date


_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _require_non_empty(value: str, field_name: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise ValueError(f"{field_name} must not be empty.")
    return cleaned


def validate_safe_name(value: str, field_name: str) -> str:
    cleaned = _require_non_empty(value, field_name)
    if not _SAFE_NAME_RE.match(cleaned):
        raise ValueError(
            f"Unsafe {field_name}: {cleaned!r}. "
            "Use only letters, numbers, underscore, and dash."
        )
    return cleaned


def validate_run_date(run_date: str) -> str:
    cleaned = _require_non_empty(run_date, "run_date")
    try:
        date.fromisoformat(cleaned)
    except ValueError as exc:
        raise ValueError("run_date must use YYYY-MM-DD format.") from exc
    return cleaned


def validate_run_id(run_id: str) -> str:
    return validate_safe_name(run_id, "run_id")


def validate_source_name(source_name: str) -> str:
    return validate_safe_name(source_name, "source_name")


def validate_job_name(job_name: str) -> str:
    return validate_safe_name(job_name, "job_name")


def _with_bucket(path: str, bucket: str | None = None) -> str:
    clean_bucket = str(bucket or "").strip().strip("/")
    if not clean_bucket:
        return path
    return f"gs://{clean_bucket}/{path}"


def _run_scope_segment(run_id: str | None = None) -> str:
    if not run_id:
        return ""
    return f"run_id={validate_run_id(run_id)}/"


def bronze_prefix(source_name: str, run_date: str, bucket: str | None = None, run_id: str | None = None) -> str:
    source = validate_source_name(source_name)
    date_value = validate_run_date(run_date)
    return _with_bucket(f"bronze/{source}/run_date={date_value}/{_run_scope_segment(run_id)}", bucket)


def silver_prefix(run_date: str, bucket: str | None = None, run_id: str | None = None) -> str:
    date_value = validate_run_date(run_date)
    return _with_bucket(f"silver/run_date={date_value}/{_run_scope_segment(run_id)}", bucket)


def gold_prefix(run_date: str, bucket: str | None = None, run_id: str | None = None) -> str:
    date_value = validate_run_date(run_date)
    return _with_bucket(f"gold/run_date={date_value}/{_run_scope_segment(run_id)}", bucket)


def analytics_prefix(run_date: str, bucket: str | None = None, run_id: str | None = None) -> str:
    date_value = validate_run_date(run_date)
    return _with_bucket(f"analytics/run_date={date_value}/{_run_scope_segment(run_id)}", bucket)


def source_manifest_path(run_date: str, bucket: str | None = None, run_id: str | None = None) -> str:
    date_value = validate_run_date(run_date)
    return _with_bucket(
        f"manifests/source_manifest/run_date={date_value}/{_run_scope_segment(run_id)}source_manifest.json",
        bucket,
    )


def pipeline_manifest_path(run_date: str, bucket: str | None = None, run_id: str | None = None) -> str:
    date_value = validate_run_date(run_date)
    return _with_bucket(
        f"manifests/pipeline_manifest/run_date={date_value}/{_run_scope_segment(run_id)}pipeline_manifest.json",
        bucket,
    )


def data_quality_report_path(run_date: str, bucket: str | None = None, run_id: str | None = None) -> str:
    date_value = validate_run_date(run_date)
    return _with_bucket(
        f"reports/data_quality/run_date={date_value}/{_run_scope_segment(run_id)}data_quality_report.json",
        bucket,
    )


def build_layout(
    run_date: str,
    sources: list[str] | tuple[str, ...],
    bucket: str | None = None,
    run_id: str | None = None,
) -> dict:
    date_value = validate_run_date(run_date)
    source_names = sorted(validate_source_name(source) for source in sources)
    return {
        "bronze": {
            source: bronze_prefix(source, date_value, bucket, run_id=run_id)
            for source in source_names
        },
        "silver": silver_prefix(date_value, bucket, run_id=run_id),
        "gold": gold_prefix(date_value, bucket, run_id=run_id),
        "analytics": analytics_prefix(date_value, bucket, run_id=run_id),
        "source_manifest": source_manifest_path(date_value, bucket, run_id=run_id),
        "pipeline_manifest": pipeline_manifest_path(date_value, bucket, run_id=run_id),
        "data_quality_report": data_quality_report_path(date_value, bucket, run_id=run_id),
    }
