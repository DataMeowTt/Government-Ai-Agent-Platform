from __future__ import annotations

from ops.ops_writer import PIPELINE_RUN_METADATA_REQUIRED, build_ops_writer_plan
from ops.pipeline_run_metadata import PipelineRunMetadata
from ops.records import build_pipeline_run_metadata_record


def _metadata() -> PipelineRunMetadata:
    return PipelineRunMetadata(
        run_id="run-1",
        run_date="2026-05-24",
        execution_mode="scheduled",
        status="SUCCESS",
        started_at="2026-05-24T02:00:00Z",
        finished_at="2026-05-24T02:10:00Z",
        enabled_sources=["wdi"],
        source_changed=True,
        change_reason="official source changed",
        candidate_source_manifest_path="/tmp/candidate.json",
        baseline_success_manifest_path="/tmp/baseline.json",
        changed_sources=["wdi"],
        validation_status="passed",
        data_quality_status="passed",
        bronze_write_planned=True,
        bronze_write_performed=False,
        warehouse_publish_planned=True,
        warehouse_publish_performed=False,
        last_successful_updated=True,
        last_successful_run_id="run-0",
        last_successful_run_date="2026-04-24",
        published_at="2026-05-24T02:09:59Z",
        latest_data_year=2025,
        sources_json='[{"name":"wdi","version":null,"updated_at":null}]',
        error_message=None,
        force_requested=False,
        force_applied=False,
        planned_actions=[{"action": "publish_bigquery_production_if_valid"}],
        cloud_write=False,
        publish_performed=False,
    )


def _metadata_entry(plan: list[dict]) -> dict:
    return next(entry for entry in plan if entry["table"] == "pipeline_run_metadata")


def test_pipeline_run_metadata_validates_and_stays_dry_run() -> None:
    record = build_pipeline_run_metadata_record(_metadata())
    plan = build_ops_writer_plan({"pipeline_run_metadata": [record]}, project_id="western-pivot-452008-a6")
    entry = _metadata_entry(plan)

    assert entry["dry_run"] is True
    assert entry["row_count"] == 1
    assert entry["rows_preview"] == [record]
    assert entry["validation"]["status"] == "passed"
    assert entry["validation"]["required_fields"] == list(PIPELINE_RUN_METADATA_REQUIRED)
    assert "write_performed" not in entry
    assert "warehouse_operation_performed" not in entry


def test_pipeline_run_metadata_missing_required_field_fails_validation() -> None:
    record = build_pipeline_run_metadata_record(_metadata())
    record.pop("sources_json")
    plan = build_ops_writer_plan({"pipeline_run_metadata": [record]}, project_id="western-pivot-452008-a6")
    entry = _metadata_entry(plan)

    assert entry["dry_run"] is True
    assert entry["validation"]["status"] == "failed"
    assert entry["validation"]["required_fields"] == list(PIPELINE_RUN_METADATA_REQUIRED)
    assert "sources_json" in entry["validation"]["required_fields"]
    assert "write_performed" not in entry
    assert "warehouse_operation_performed" not in entry
