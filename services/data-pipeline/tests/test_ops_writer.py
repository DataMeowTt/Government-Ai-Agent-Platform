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
        candidate_source_manifest_path="gs://bucket/manifests/source_manifest/run_date=2026-05-24/source_manifest.json",
        baseline_success_manifest_path="gs://bucket/manifests/source_manifest/run_date=2026-05-01/source_manifest.json",
        changed_sources=["wdi"],
        validation_status="passed",
        data_quality_status="passed",
        bronze_write_planned=True,
        bronze_write_performed=False,
        warehouse_publish_planned=True,
        warehouse_publish_performed=True,
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
        cloud_write=True,
        publish_performed=True,
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
    assert entry["validation"]["row_errors"] == []
    assert "write_performed" not in entry
    assert "warehouse_operation_performed" not in entry


def test_pipeline_run_metadata_missing_required_field_fails_validation() -> None:
    record = build_pipeline_run_metadata_record(_metadata())
    record.pop("started_at")
    plan = build_ops_writer_plan({"pipeline_run_metadata": [record]}, project_id="western-pivot-452008-a6")
    entry = _metadata_entry(plan)

    assert entry["dry_run"] is True
    assert entry["validation"]["status"] == "failed"
    assert entry["validation"]["required_fields"] == list(PIPELINE_RUN_METADATA_REQUIRED)
    assert "started_at" in entry["validation"]["required_fields"]
    assert any(
        "started_at" in row_error["missing_fields"]
        for row_error in entry["validation"]["row_errors"]
    )
    assert "write_performed" not in entry
    assert "warehouse_operation_performed" not in entry


def test_success_status_rejects_publish_performed_false() -> None:
    record = build_pipeline_run_metadata_record(_metadata())
    record["publish_performed"] = False
    plan = build_ops_writer_plan({"pipeline_run_metadata": [record]}, project_id="western-pivot-452008-a6")
    entry = _metadata_entry(plan)

    assert entry["validation"]["status"] == "failed"
    assert any(
        "SUCCESS requires publish_performed=True" in row_error["semantic_errors"]
        for row_error in entry["validation"]["row_errors"]
    )


def test_success_status_rejects_warehouse_publish_performed_false() -> None:
    record = build_pipeline_run_metadata_record(_metadata())
    record["warehouse_publish_performed"] = False
    plan = build_ops_writer_plan({"pipeline_run_metadata": [record]}, project_id="western-pivot-452008-a6")
    entry = _metadata_entry(plan)

    assert entry["validation"]["status"] == "failed"
    assert any(
        "SUCCESS requires warehouse_publish_performed=True" in row_error["semantic_errors"]
        for row_error in entry["validation"]["row_errors"]
    )


def test_success_status_accepts_first_run_with_baseline_none() -> None:
    record = build_pipeline_run_metadata_record(_metadata())
    record["baseline_success_manifest_path"] = None
    plan = build_ops_writer_plan({"pipeline_run_metadata": [record]}, project_id="western-pivot-452008-a6")
    entry = _metadata_entry(plan)

    assert entry["validation"]["status"] == "passed"


def test_success_rejects_missing_candidate_source_manifest_path() -> None:
    record = build_pipeline_run_metadata_record(_metadata())
    record.pop("candidate_source_manifest_path")
    plan = build_ops_writer_plan({"pipeline_run_metadata": [record]}, project_id="western-pivot-452008-a6")
    entry = _metadata_entry(plan)

    assert entry["validation"]["status"] == "failed"
    assert any(
        "SUCCESS requires candidate_source_manifest_path to be non-empty" in row_error["semantic_errors"]
        for row_error in entry["validation"]["row_errors"]
    )


def test_success_rejects_blank_candidate_source_manifest_path() -> None:
    record = build_pipeline_run_metadata_record(_metadata())
    record["candidate_source_manifest_path"] = "   "
    plan = build_ops_writer_plan({"pipeline_run_metadata": [record]}, project_id="western-pivot-452008-a6")
    entry = _metadata_entry(plan)

    assert entry["validation"]["status"] == "failed"
    assert any(
        "SUCCESS requires candidate_source_manifest_path to be non-empty" in row_error["semantic_errors"]
        for row_error in entry["validation"]["row_errors"]
    )


def test_success_rejects_local_candidate_source_manifest_path() -> None:
    record = build_pipeline_run_metadata_record(_metadata())
    record["candidate_source_manifest_path"] = "/tmp/source_manifest.json"
    plan = build_ops_writer_plan({"pipeline_run_metadata": [record]}, project_id="western-pivot-452008-a6")
    entry = _metadata_entry(plan)

    assert entry["validation"]["status"] == "failed"
    assert any(
        "SUCCESS requires candidate_source_manifest_path to be a durable gs:// URI" in row_error["semantic_errors"]
        for row_error in entry["validation"]["row_errors"]
    )


def test_success_rejects_non_gcs_candidate_source_manifest_path() -> None:
    record = build_pipeline_run_metadata_record(_metadata())
    record["candidate_source_manifest_path"] = "https://example.com/source_manifest.json"
    plan = build_ops_writer_plan({"pipeline_run_metadata": [record]}, project_id="western-pivot-452008-a6")
    entry = _metadata_entry(plan)

    assert entry["validation"]["status"] == "failed"
    assert any(
        "SUCCESS requires candidate_source_manifest_path to be a durable gs:// URI" in row_error["semantic_errors"]
        for row_error in entry["validation"]["row_errors"]
    )


def test_planned_changed_rejects_success_publish_flags_or_published_at() -> None:
    record = build_pipeline_run_metadata_record(_metadata())
    record["status"] = "PLANNED_CHANGED"
    record["warehouse_publish_performed"] = True
    record["publish_performed"] = True
    record["last_successful_updated"] = False
    record["published_at"] = "2026-05-24T02:09:59Z"
    plan = build_ops_writer_plan({"pipeline_run_metadata": [record]}, project_id="western-pivot-452008-a6")
    entry = _metadata_entry(plan)

    assert entry["validation"]["status"] == "failed"
    assert any(
        "PLANNED_CHANGED requires warehouse_publish_performed=False" in row_error["semantic_errors"]
        for row_error in entry["validation"]["row_errors"]
    )
    assert any(
        "PLANNED_CHANGED requires publish_performed=False" in row_error["semantic_errors"]
        for row_error in entry["validation"]["row_errors"]
    )
    assert any(
        "PLANNED_CHANGED requires published_at to be empty" in row_error["semantic_errors"]
        for row_error in entry["validation"]["row_errors"]
    )


def test_blocked_approval_required_allows_non_publish_shape() -> None:
    record = build_pipeline_run_metadata_record(_metadata())
    record["status"] = "BLOCKED_APPROVAL_REQUIRED"
    record["warehouse_publish_performed"] = False
    record["publish_performed"] = False
    record["last_successful_updated"] = False
    record["published_at"] = None
    plan = build_ops_writer_plan({"pipeline_run_metadata": [record]}, project_id="western-pivot-452008-a6")
    entry = _metadata_entry(plan)

    assert entry["validation"]["status"] == "passed"


def test_blocked_approval_required_rejects_success_like_flags() -> None:
    record = build_pipeline_run_metadata_record(_metadata())
    record["status"] = "BLOCKED_APPROVAL_REQUIRED"
    record["warehouse_publish_performed"] = True
    record["publish_performed"] = True
    record["last_successful_updated"] = True
    record["published_at"] = "2026-05-24T02:10:00Z"
    plan = build_ops_writer_plan({"pipeline_run_metadata": [record]}, project_id="western-pivot-452008-a6")
    entry = _metadata_entry(plan)

    assert entry["validation"]["status"] == "failed"
    assert any(
        "BLOCKED_APPROVAL_REQUIRED requires warehouse_publish_performed=False" in row_error["semantic_errors"]
        for row_error in entry["validation"]["row_errors"]
    )
    assert any(
        "BLOCKED_APPROVAL_REQUIRED requires publish_performed=False" in row_error["semantic_errors"]
        for row_error in entry["validation"]["row_errors"]
    )
    assert any(
        "BLOCKED_APPROVAL_REQUIRED requires last_successful_updated=False" in row_error["semantic_errors"]
        for row_error in entry["validation"]["row_errors"]
    )
    assert any(
        "BLOCKED_APPROVAL_REQUIRED requires published_at to be empty" in row_error["semantic_errors"]
        for row_error in entry["validation"]["row_errors"]
    )


def test_partial_failed_rejects_success_like_flags() -> None:
    record = build_pipeline_run_metadata_record(_metadata())
    record["status"] = "PARTIAL_FAILED"
    record["warehouse_publish_performed"] = True
    record["publish_performed"] = True
    record["last_successful_updated"] = True
    record["published_at"] = "2026-05-24T02:10:00Z"
    plan = build_ops_writer_plan({"pipeline_run_metadata": [record]}, project_id="western-pivot-452008-a6")
    entry = _metadata_entry(plan)

    assert entry["validation"]["status"] == "failed"
    assert any(
        "PARTIAL_FAILED requires warehouse_publish_performed=False" in row_error["semantic_errors"]
        for row_error in entry["validation"]["row_errors"]
    )
