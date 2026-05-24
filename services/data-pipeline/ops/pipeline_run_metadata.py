from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PipelineRunMetadata:
    run_id: str
    run_date: str
    execution_mode: str
    status: str
    started_at: str
    finished_at: str | None
    enabled_sources: list[str]
    source_changed: bool | None
    change_reason: str | None
    candidate_source_manifest_path: str | None
    baseline_success_manifest_path: str | None
    changed_sources: list[str]
    validation_status: str | None
    data_quality_status: str | None
    bronze_write_planned: bool
    bronze_write_performed: bool
    warehouse_publish_planned: bool
    warehouse_publish_performed: bool
    last_successful_updated: bool
    last_successful_run_id: str | None
    last_successful_run_date: str | None
    published_at: str | None
    latest_data_year: int | None
    sources_json: str | None
    error_message: str | None
    force_requested: bool
    force_applied: bool
    planned_actions: list[dict[str, Any]]
    cloud_write: bool
    publish_performed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_default_metadata(
    *,
    run_id: str,
    run_date: str,
    execution_mode: str,
    enabled_sources: list[str],
    force_requested: bool,
) -> PipelineRunMetadata:
    return PipelineRunMetadata(
        run_id=run_id,
        run_date=run_date,
        execution_mode=execution_mode,
        status="FAILED",
        started_at=utc_now_iso(),
        finished_at=None,
        enabled_sources=enabled_sources,
        source_changed=None,
        change_reason=None,
        candidate_source_manifest_path=None,
        baseline_success_manifest_path=None,
        changed_sources=[],
        validation_status=None,
        data_quality_status=None,
        bronze_write_planned=False,
        bronze_write_performed=False,
        warehouse_publish_planned=False,
        warehouse_publish_performed=False,
        last_successful_updated=False,
        last_successful_run_id=None,
        last_successful_run_date=None,
        published_at=None,
        latest_data_year=None,
        sources_json=None,
        error_message=None,
        force_requested=force_requested,
        force_applied=False,
        planned_actions=[],
        cloud_write=False,
        publish_performed=False,
    )
