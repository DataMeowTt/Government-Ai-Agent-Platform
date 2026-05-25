from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from jobs import scheduled_pipeline
from warehouse.bigquery_recovery import PRODUCTION_TABLE_ORDER


def _manifest(fingerprint: str, status: str = "valid") -> dict[str, Any]:
    return {
        "run_id": "run-1",
        "run_date": "2026-05-24",
        "status": status,
        "sources": [{"source_name": "wdi", "combined_fingerprint": fingerprint}],
    }


def _write_baseline(path: Path, fingerprint: str) -> None:
    path.write_text(json.dumps(_manifest(fingerprint)), encoding="utf-8")


def _prepare_runtime_raw(tmp_path: Path) -> Path:
    runtime_raw = tmp_path / "runtime" / "raw"
    (runtime_raw / "worldBank").mkdir(parents=True, exist_ok=True)
    (runtime_raw / "gmd").mkdir(parents=True, exist_ok=True)
    (runtime_raw / "Macro-Statistics_Key_Indicators_E_All_Data_(Normalized)").mkdir(parents=True, exist_ok=True)
    (runtime_raw / "worldBank" / "WDICSV.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (runtime_raw / "gmd" / "GMD.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (runtime_raw / "Macro-Statistics_Key_Indicators_E_All_Data_(Normalized)" / "Macro-Statistics_Key_Indicators_E_All_Data_(Normalized).csv").write_text(
        "a,b\n1,2\n",
        encoding="utf-8",
    )
    return runtime_raw


def _run(
    tmp_path: Path,
    args: list[str],
    *,
    deps: scheduled_pipeline.Dependencies | None = None,
) -> tuple[int, dict[str, Any], dict[str, Any]]:
    runtime_dir = tmp_path / "runtime"
    output_dir = tmp_path / "out"
    code = scheduled_pipeline.run(
        [
            *args,
            "--runtime-dir",
            str(runtime_dir),
            "--output-dir",
            str(output_dir),
        ],
        deps=deps,
    )
    result = json.loads((output_dir / "scheduled_pipeline_result.json").read_text(encoding="utf-8"))
    metadata = json.loads((output_dir / "pipeline_run_metadata.json").read_text(encoding="utf-8"))
    return code, result, metadata


def _deps_no_cloud_baseline(**kwargs: Any) -> scheduled_pipeline.Dependencies:
    base: dict[str, Any] = {
        "read_success_metadata_rows": lambda **_: [],
        "fetch_manifest_text": lambda _uri: (_ for _ in ()).throw(AssertionError("baseline fetch should not run")),
    }
    base.update(kwargs)
    return scheduled_pipeline.Dependencies(**base)


def _mock_recovery_ready(production_table_ids: list[str], retention_days: int) -> dict[str, Any]:
    return {
        "status": "RECOVERY_READY",
        "retention_days": retention_days,
        "backups": [
            {
                "production_table_id": table_id,
                "recovery_table_id": f"{table_id}_recovery",
                "copy_job_id": "job-1",
                "source_row_count": 1,
                "recovery_row_count": 1,
                "expiration_time_utc": "2026-07-08T00:00:00+00:00",
            }
            for table_id in production_table_ids
        ],
    }


def _canonical_publish_tables(*, row_count: int) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    for table_id in PRODUCTION_TABLE_ORDER[1:]:
        _, dataset, table = table_id.split(".", 2)
        tables.append(
            {
                "dataset": dataset,
                "staging_table": f"{table}_staging_run_run_1",
                "production_table": table,
                "row_count": row_count,
            }
        )
    return tables


def test_run_build_silver_candidate_failure_surfaces_non_warning_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Result:
        returncode = 1
        stdout = ""
        stderr = "\n".join(
            [
                "WARNING: Using incubator modules: jdk.incubator.vector",
                "Traceback (most recent call last):",
                "RuntimeError: parquet write failed",
            ]
        )

    monkeypatch.setattr(scheduled_pipeline.subprocess, "run", lambda *_a, **_k: _Result())

    with pytest.raises(RuntimeError) as exc_info:
        scheduled_pipeline._run_build_silver_candidate(
            run_id="run-1",
            run_date="2026-05-24",
            output_dir=tmp_path / "out",
            source="all",
            output_format="parquet",
            wdi_path=tmp_path / "wdi",
            gmd_path=tmp_path / "gmd",
            fao_macro_path=tmp_path / "fao",
        )

    message = str(exc_info.value)
    assert "exit_code=1" in message
    assert "RuntimeError: parquet write failed" in message
    assert "reason=WARNING: Using incubator modules" not in message


def test_run_build_silver_candidate_failure_uses_stdout_when_stderr_is_only_low_signal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Result:
        returncode = 1
        stdout = "\n".join(
            [
                "[Stage 1:>                                                        (0 + 1) / 1]",
                "ValueError: failed to parse source row",
            ]
        )
        stderr = "\n".join(
            [
                "WARNING: Using incubator modules: jdk.incubator.vector",
                "Using Spark's default log4j profile: org/apache/spark/log4j2-defaults.properties",
            ]
        )

    monkeypatch.setattr(scheduled_pipeline.subprocess, "run", lambda *_a, **_k: _Result())

    with pytest.raises(RuntimeError) as exc_info:
        scheduled_pipeline._run_build_silver_candidate(
            run_id="run-1",
            run_date="2026-05-24",
            output_dir=tmp_path / "out",
            source="all",
            output_format="parquet",
            wdi_path=tmp_path / "wdi",
            gmd_path=tmp_path / "gmd",
            fao_macro_path=tmp_path / "fao",
        )

    message = str(exc_info.value)
    assert "ValueError: failed to parse source row" in message
    assert "exit_code=1" in message


def test_plan_mode_keeps_no_write_behavior(tmp_path: Path) -> None:
    code, result, metadata = _run(
        tmp_path,
        ["--mode", "plan", "--run-id", "run-1", "--run-date", "2026-05-24"],
    )
    assert code == 0
    assert metadata["status"] == "PLANNED_UNCHANGED"
    assert result["publish_performed"] is False
    assert metadata["cloud_write"] is False


def test_dry_run_without_allow_network_blocks_safely(tmp_path: Path) -> None:
    code, _result, metadata = _run(
        tmp_path,
        ["--mode", "dry_run", "--run-id", "run-1", "--run-date", "2026-05-24"],
    )
    assert code == 1
    assert metadata["status"] == "ACQUISITION_FAILED"
    assert metadata["source_changed"] is None
    assert metadata["publish_performed"] is False


def test_allow_network_wiring_present_for_acquisition(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run_acquisition(*, args: argparse.Namespace, selected_sources: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        captured["allow_network"] = args.allow_network
        captured["selected_sources"] = selected_sources
        return _manifest("same"), []

    monkeypatch.setattr(scheduled_pipeline, "run_acquisition", fake_run_acquisition)
    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline, "same")
    code, _result, metadata = _run(
        tmp_path,
        [
            "--mode",
            "dry_run",
            "--run-id",
            "run-1",
            "--run-date",
            "2026-05-24",
            "--allow-network",
            "--previous-success-manifest",
            str(baseline),
        ],
    )
    assert code == 0
    assert captured["allow_network"] is True
    assert metadata["status"] == "SKIPPED_UNCHANGED"


def test_execute_default_baseline_reads_latest_success_and_fetches_candidate_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_raw = _prepare_runtime_raw(tmp_path)
    monkeypatch.setattr(
        scheduled_pipeline,
        "run_acquisition",
        lambda **_: (
            {
                "run_id": "run-1",
                "run_date": "2026-05-24",
                "status": "valid",
                "sources": [
                    {
                        "source_name": "wdi",
                        "combined_fingerprint": "same",
                        "runtime_materialized_path": str((runtime_raw / "worldBank").resolve()),
                        "validation_status": "valid",
                    }
                ],
            },
            [],
        ),
    )

    candidate_uri = "gs://bucket/manifests/source_manifest/run_date=2026-05-01/source_manifest.json"
    baseline_uri = "gs://bucket/manifests/source_manifest/run_date=2026-04-01/source_manifest.json"
    metadata_calls: list[str] = []
    fetch_calls: list[str] = []

    def fake_reader(*, project_id: str, table_id: str) -> list[dict[str, Any]]:
        metadata_calls.append(f"{project_id}:{table_id}")
        return [
            {
                "run_id": "run-success",
                "status": "SUCCESS",
                "warehouse_publish_performed": True,
                "publish_performed": True,
                "last_successful_updated": True,
                "published_at": "2026-05-02T00:00:00Z",
                "candidate_source_manifest_path": candidate_uri,
                "baseline_success_manifest_path": baseline_uri,
            }
        ]

    def fake_fetch(uri: str) -> str:
        fetch_calls.append(uri)
        return json.dumps(_manifest("same"))

    deps = scheduled_pipeline.Dependencies(
        read_success_metadata_rows=fake_reader,
        fetch_manifest_text=fake_fetch,
        execute_upload_plan_fn=lambda _plan: (_ for _ in ()).throw(AssertionError("upload must not run")),
        append_metadata_row=lambda **_: (_ for _ in ()).throw(AssertionError("metadata append must not run")),
    )
    code, result, metadata = _run(
        tmp_path,
        ["--mode", "execute", "--run-id", "run-1", "--run-date", "2026-05-24", "--allow-network"],
        deps=deps,
    )

    assert code == 0
    assert metadata["status"] == "SKIPPED_UNCHANGED"
    assert result["status"] == "SKIPPED_UNCHANGED"
    assert metadata_calls == ["western-pivot-452008-a6:western-pivot-452008-a6.gov_ai_ops.pipeline_run_metadata"]
    assert fetch_calls == [candidate_uri]
    assert baseline_uri not in fetch_calls
    assert metadata["candidate_source_manifest_path"].startswith(str((tmp_path / "out").resolve()))
    assert metadata["baseline_success_manifest_path"] == candidate_uri


def test_execute_malformed_fetched_baseline_returns_baseline_invalid_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_raw = _prepare_runtime_raw(tmp_path)
    monkeypatch.setattr(
        scheduled_pipeline,
        "run_acquisition",
        lambda **_: (
            {
                "run_id": "run-1",
                "run_date": "2026-05-24",
                "status": "valid",
                "sources": [
                    {
                        "source_name": "wdi",
                        "combined_fingerprint": "new",
                        "runtime_materialized_path": str((runtime_raw / "worldBank").resolve()),
                        "present_files": ["WDICSV.csv"],
                        "validation_status": "valid",
                    }
                ],
            },
            [],
        ),
    )
    reads = {"metadata": 0, "fetch": 0, "upload": 0}
    deps = scheduled_pipeline.Dependencies(
        read_success_metadata_rows=lambda **_: [
            {
                "run_id": "run-success",
                "status": "SUCCESS",
                "warehouse_publish_performed": True,
                "publish_performed": True,
                "last_successful_updated": True,
                "published_at": "2026-05-02T00:00:00Z",
                "candidate_source_manifest_path": "gs://bucket/manifests/source_manifest/run_date=2026-05-01/source_manifest.json",
            }
        ],
        fetch_manifest_text=lambda _uri: (reads.__setitem__("fetch", reads["fetch"] + 1) or json.dumps({"bad": "shape"})),
        execute_upload_plan_fn=lambda _plan: (reads.__setitem__("upload", reads["upload"] + 1) or {"status": "uploaded"}),
        verify_uploaded_source_manifest=lambda **_: {"status": "VERIFIED", "matched": True},
    )
    code, result, metadata = _run(
        tmp_path,
        ["--mode", "execute", "--run-id", "run-1", "--run-date", "2026-05-24", "--allow-network"],
        deps=deps,
    )
    reads["metadata"] = 1
    assert code == 1
    assert metadata["status"] == "BASELINE_INVALID"
    assert result["status"] == "BASELINE_INVALID"
    assert reads["fetch"] == 1
    assert reads["upload"] == 0


def test_execute_changed_branch_blocks_after_read_only_baseline_without_cloud_write_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_raw = _prepare_runtime_raw(tmp_path)
    monkeypatch.setattr(
        scheduled_pipeline,
        "run_acquisition",
        lambda **_: (
            {
                "run_id": "run-1",
                "run_date": "2026-05-24",
                "status": "valid",
                "sources": [
                    {
                        "source_name": "wdi",
                        "combined_fingerprint": "new",
                        "runtime_materialized_path": str((runtime_raw / "worldBank").resolve()),
                        "present_files": ["WDICSV.csv"],
                        "validation_status": "valid",
                    }
                ],
            },
            [],
        ),
    )

    calls = {"metadata": 0, "fetch": 0, "upload": 0}

    deps = scheduled_pipeline.Dependencies(
        read_success_metadata_rows=lambda **_: (
            calls.__setitem__("metadata", calls["metadata"] + 1)
            or [
                {
                    "run_id": "run-success",
                    "status": "SUCCESS",
                    "warehouse_publish_performed": True,
                    "publish_performed": True,
                    "last_successful_updated": True,
                    "published_at": "2026-05-02T00:00:00Z",
                    "candidate_source_manifest_path": "gs://bucket/manifests/source_manifest/run_date=2026-05-01/source_manifest.json",
                }
            ]
        ),
        fetch_manifest_text=lambda _uri: (calls.__setitem__("fetch", calls["fetch"] + 1) or json.dumps(_manifest("old"))),
        execute_upload_plan_fn=lambda _plan: (calls.__setitem__("upload", calls["upload"] + 1) or {"status": "uploaded"}),
        verify_uploaded_source_manifest=lambda **_: {"status": "VERIFIED", "matched": True},
    )

    code, result, metadata = _run(
        tmp_path,
        ["--mode", "execute", "--run-id", "run-1", "--run-date", "2026-05-24", "--allow-network"],
        deps=deps,
    )
    assert code == 0
    assert metadata["status"] == "BLOCKED_APPROVAL_REQUIRED"
    assert result["status"] == "BLOCKED_APPROVAL_REQUIRED"
    assert calls["metadata"] == 1
    assert calls["fetch"] == 1
    assert calls["upload"] == 0
    assert metadata["publish_performed"] is False
    assert metadata["last_successful_updated"] is False


def test_execute_candidate_first_ordering_and_success_metadata_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_raw = _prepare_runtime_raw(tmp_path)
    monkeypatch.setenv("CLOUD_WRITE_APPROVED", "true")
    monkeypatch.setenv("BIGQUERY_WRITE_APPROVED", "true")
    monkeypatch.setenv("BIGQUERY_WAREHOUSE_WRITE_APPROVED", "true")
    monkeypatch.setenv("BIGQUERY_OPS_WRITE_APPROVED", "true")

    monkeypatch.setattr(
        scheduled_pipeline,
        "run_acquisition",
        lambda **_: (
            {
                "run_id": "run-1",
                "run_date": "2026-05-24",
                "status": "valid",
                "sources": [
                    {
                        "source_name": "wdi",
                        "combined_fingerprint": "new",
                        "runtime_materialized_path": str((runtime_raw / "worldBank").resolve()),
                        "present_files": ["WDICSV.csv"],
                        "validation_status": "valid",
                    },
                    {
                        "source_name": "gmd",
                        "combined_fingerprint": "new-gmd",
                        "runtime_materialized_path": str((runtime_raw / "gmd").resolve()),
                        "present_files": ["GMD.csv"],
                        "validation_status": "valid",
                    },
                    {
                        "source_name": "fao_macro",
                        "combined_fingerprint": "new-fao",
                        "runtime_materialized_path": str(
                            (runtime_raw / "Macro-Statistics_Key_Indicators_E_All_Data_(Normalized)").resolve()
                        ),
                        "present_files": ["Macro-Statistics_Key_Indicators_E_All_Data_(Normalized).csv"],
                        "validation_status": "valid",
                    },
                ],
            },
            [],
        ),
    )

    call_order: list[str] = []

    def fake_build_silver_candidate(**_kwargs: Any) -> dict[str, Any]:
        call_order.append("build_silver")
        silver_dir = tmp_path / "silver_output"
        silver_dir.mkdir(parents=True, exist_ok=True)
        return {
            "manifest_path": str(tmp_path / "silver_manifest.json"),
            "manifest": {"validation_summary": {"row_count": 3}},
            "silver_output_path": str(silver_dir),
        }

    def fake_stage_silver_candidate(**_kwargs: Any) -> dict[str, Any]:
        call_order.append("stage_silver")
        return {
            "result": {"staging_table_id": "western-pivot-452008-a6.gov_ai_silver.silver_indicators_staging_run_run_1"},
            "validation": {"local_validation": {"row_count": 3}},
        }

    class _Candidate:
        def __init__(self, name: str) -> None:
            self.dataset = "gov_ai_gold"
            self.production_table = name
            self.production_table_id = f"western-pivot-452008-a6.gov_ai_gold.{name}"
            self.staging_table_id = f"western-pivot-452008-a6.gov_ai_gold.{name}_staging"
            self.staging_table = f"{name}_staging"
            self.local_row_count = 3
            self.staging_row_count = 3
            self.staging_columns = ["country_code", "year"]
            self.load_job_id = f"load-{name}"

    canonical_tables = _canonical_publish_tables(row_count=3)

    def fake_rebuild_warehouse(**_kwargs: Any) -> dict[str, Any]:
        return {
            "silver_preflight": {"year_max": 2025},
            "gold_summary": [
                {"table_name": item["production_table"], "parquet_path": str(tmp_path / f"{item['production_table']}.parquet")}
                for item in canonical_tables
                if item["dataset"] == "gov_ai_gold"
            ],
            "analytics_summary": [
                {"table_name": item["production_table"], "parquet_path": str(tmp_path / f"{item['production_table']}.parquet")}
                for item in canonical_tables
                if item["dataset"] == "gov_ai_analytics"
            ],
            "publish_plan": {"tables": canonical_tables},
        }

    def fake_stage_warehouse_candidate(*, production_table: str, **_kwargs: Any) -> Any:
        call_order.append(f"stage_{production_table}")
        return _Candidate(production_table)

    def fake_promote_silver_candidate_fn(**_kwargs: Any) -> dict[str, Any]:
        call_order.append("promote_silver")
        return {"target_table_id": "western-pivot-452008-a6.gov_ai_silver.silver_indicators"}

    def fake_promote_warehouse_candidate(*, candidate: Any, **_kwargs: Any) -> Any:
        call_order.append(f"promote_{candidate.production_table}")

        class _Promoted:
            dataset = candidate.dataset
            production_table_id = candidate.production_table_id
            staging_table_id = candidate.staging_table_id

        return _Promoted()

    writes: list[dict[str, Any]] = []

    def fake_append_metadata_row(**kwargs: Any) -> dict[str, Any]:
        call_order.append("metadata_write")
        writes.append(kwargs)
        return {"table_id": "western-pivot-452008-a6.gov_ai_ops.pipeline_run_metadata"}

    deps = scheduled_pipeline.Dependencies(
        read_success_metadata_rows=lambda **_: [],
        build_silver_candidate=fake_build_silver_candidate,
        build_silver_load_plan_fn=lambda **_: {
            "bigquery_write_approved": False,
            "cluster": ["country_code", "indicator", "source"],
            "dataset": "gov_ai_silver",
            "dry_run": True,
            "job_started": False,
            "local_manifest_path": str(tmp_path / "silver_manifest.json"),
            "local_silver_path": str(tmp_path / "silver_output"),
            "location": "asia-southeast1",
            "partition": {"type": "integer_range", "column": "year", "start": 1980, "end": 2031, "interval": 1},
            "project_id": "western-pivot-452008-a6",
            "row_count": 3,
            "source_counts": {"wdi": 1, "gmd": 1, "macro": 1},
            "source_format": "parquet",
            "table": "silver_indicators",
            "table_id": "western-pivot-452008-a6.gov_ai_silver.silver_indicators",
        },
        stage_silver_candidate=fake_stage_silver_candidate,
        rebuild_warehouse=fake_rebuild_warehouse,
        stage_warehouse_candidate=fake_stage_warehouse_candidate,
        run_data_quality_gate=lambda **_: (call_order.append("quality_gate") or {"status": "PASSED", "errors": [], "checked_tables": ["silver_indicators", "gold_growth_dynamics", "analytics_clusters"]}),
        promote_silver_candidate_fn=fake_promote_silver_candidate_fn,
        promote_warehouse_candidate=fake_promote_warehouse_candidate,
        recovery_retention_days=lambda *_: 45,
        prepare_recovery_backups_fn=lambda **kwargs: _mock_recovery_ready(
            production_table_ids=list(kwargs["production_table_ids"]),
            retention_days=int(kwargs["retention_days"]),
        ),
        append_metadata_row=fake_append_metadata_row,
        execute_upload_plan_fn=lambda _plan: {"status": "uploaded", "uploaded_count": 3},
        verify_uploaded_source_manifest=lambda **_: (call_order.append("verify_upload") or {"status": "VERIFIED", "matched": True}),
    )
    code, result, metadata = _run(
        tmp_path,
        ["--mode", "execute", "--run-id", "run-1", "--run-date", "2026-05-24", "--allow-network"],
        deps=deps,
    )

    assert code == 0
    assert metadata["status"] == "SUCCESS"
    assert metadata["data_quality_status"] == "PASSED"
    assert result["publish_performed"] is True
    assert len(writes) == 1
    row = writes[0]["row"]
    assert row["candidate_source_manifest_path"].startswith("gs://")
    assert row["baseline_success_manifest_path"] is None
    assert call_order.index("verify_upload") < call_order.index("stage_silver")
    assert call_order.index("stage_gold_growth_dynamics") < call_order.index("quality_gate")
    assert call_order.index("stage_analytics_clusters") < call_order.index("quality_gate")
    assert call_order.index("quality_gate") < call_order.index("promote_silver")
    assert call_order.index("promote_silver") < call_order.index("promote_gold_growth_dynamics")
    assert call_order.index("promote_gold_growth_dynamics") < call_order.index("metadata_write")


def test_execute_gate_failed_prevents_any_promotion_or_success_append(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_raw = _prepare_runtime_raw(tmp_path)
    monkeypatch.setenv("CLOUD_WRITE_APPROVED", "true")
    monkeypatch.setenv("BIGQUERY_WRITE_APPROVED", "true")
    monkeypatch.setenv("BIGQUERY_WAREHOUSE_WRITE_APPROVED", "true")
    monkeypatch.setenv("BIGQUERY_OPS_WRITE_APPROVED", "true")
    monkeypatch.setattr(
        scheduled_pipeline,
        "run_acquisition",
        lambda **_: (
            {
                "run_id": "run-1",
                "run_date": "2026-05-24",
                "status": "valid",
                "sources": [
                    {
                        "source_name": "wdi",
                        "combined_fingerprint": "new",
                        "runtime_materialized_path": str((runtime_raw / "worldBank").resolve()),
                        "present_files": ["WDICSV.csv"],
                        "validation_status": "valid",
                    }
                ],
            },
            [],
        ),
    )

    deps = scheduled_pipeline.Dependencies(
        read_success_metadata_rows=lambda **_: [],
        build_silver_candidate=lambda **_: {
            "manifest_path": str(tmp_path / "silver_manifest.json"),
            "manifest": {"validation_summary": {"row_count": 3}},
            "silver_output_path": str(tmp_path / "silver_output"),
        },
        build_silver_load_plan_fn=lambda **_: {
            "bigquery_write_approved": False,
            "cluster": ["country_code", "indicator", "source"],
            "dataset": "gov_ai_silver",
            "dry_run": True,
            "job_started": False,
            "local_manifest_path": str(tmp_path / "silver_manifest.json"),
            "local_silver_path": str(tmp_path / "silver_output"),
            "location": "asia-southeast1",
            "partition": {"type": "integer_range", "column": "year", "start": 1980, "end": 2031, "interval": 1},
            "project_id": "western-pivot-452008-a6",
            "row_count": 3,
            "source_counts": {"wdi": 1, "gmd": 1, "macro": 1},
            "source_format": "parquet",
            "table": "silver_indicators",
            "table_id": "western-pivot-452008-a6.gov_ai_silver.silver_indicators",
        },
        stage_silver_candidate=lambda **_: {
            "result": {"staging_table_id": "western-pivot-452008-a6.gov_ai_silver.silver_indicators_staging_run_run_1"},
            "validation": {"local_validation": {"row_count": 3}},
        },
        rebuild_warehouse=lambda **_: {
            "silver_preflight": {"year_max": 2025},
            "gold_summary": [{"table_name": "gold_growth_dynamics", "parquet_path": str(tmp_path / "g1.parquet")}],
            "analytics_summary": [{"table_name": "analytics_clusters", "parquet_path": str(tmp_path / "a1.parquet")}],
            "publish_plan": {
                "tables": [
                    {
                        "dataset": "gov_ai_gold",
                        "staging_table": "gold_growth_dynamics_staging_run_run_1",
                        "production_table": "gold_growth_dynamics",
                        "row_count": 3,
                    },
                    {
                        "dataset": "gov_ai_analytics",
                        "staging_table": "analytics_clusters_staging_run_run_1",
                        "production_table": "analytics_clusters",
                        "row_count": 3,
                    },
                ]
            },
        },
        stage_warehouse_candidate=lambda *, production_table, **_kwargs: type(
            "Candidate",
            (),
            {
                "dataset": "gov_ai_gold",
                "production_table": production_table,
                "production_table_id": f"western-pivot-452008-a6.gov_ai_gold.{production_table}",
                "staging_table_id": f"western-pivot-452008-a6.gov_ai_gold.{production_table}_staging",
                "staging_table": f"{production_table}_staging",
                "local_row_count": 3,
                "staging_row_count": 3,
                "staging_columns": ["country_code", "year"],
                "load_job_id": "load-x",
            },
        )(),
        run_data_quality_gate=lambda **_: {"status": "FAILED", "errors": ["bad"], "checked_tables": ["silver_indicators"]},
        promote_silver_candidate_fn=lambda **_: (_ for _ in ()).throw(AssertionError("silver promote should not run")),
        promote_warehouse_candidate=lambda **_: (_ for _ in ()).throw(AssertionError("warehouse promote should not run")),
        append_metadata_row=lambda **_: (_ for _ in ()).throw(AssertionError("metadata write should not run")),
        execute_upload_plan_fn=lambda _plan: {"status": "uploaded", "uploaded_count": 1},
        verify_uploaded_source_manifest=lambda **_: {"status": "VERIFIED", "matched": True},
    )
    code, result, metadata = _run(
        tmp_path,
        ["--mode", "execute", "--run-id", "run-1", "--run-date", "2026-05-24", "--allow-network"],
        deps=deps,
    )
    assert code == 1
    assert metadata["status"] == "VALIDATION_FAILED"
    assert metadata["data_quality_status"] == "FAILED"
    assert metadata["publish_performed"] is False
    assert metadata["last_successful_updated"] is False
    assert metadata["warehouse_publish_performed"] is False
    assert result["touched_production_tables"] == []


def test_execute_validation_failure_before_any_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_raw = _prepare_runtime_raw(tmp_path)
    monkeypatch.setenv("CLOUD_WRITE_APPROVED", "true")
    monkeypatch.setenv("BIGQUERY_WRITE_APPROVED", "true")
    monkeypatch.setenv("BIGQUERY_WAREHOUSE_WRITE_APPROVED", "true")
    monkeypatch.setenv("BIGQUERY_OPS_WRITE_APPROVED", "true")
    monkeypatch.setattr(
        scheduled_pipeline,
        "run_acquisition",
        lambda **_: (
            {
                "run_id": "run-1",
                "run_date": "2026-05-24",
                "status": "valid",
                "sources": [
                    {
                        "source_name": "wdi",
                        "combined_fingerprint": "new",
                        "runtime_materialized_path": str((runtime_raw / "worldBank").resolve()),
                        "present_files": ["WDICSV.csv"],
                        "validation_status": "valid",
                    }
                ],
            },
            [],
        ),
    )

    calls: list[str] = []

    def fail_second_candidate(*, production_table: str, **_kwargs: Any) -> Any:
        calls.append(f"stage_{production_table}")
        if production_table == "analytics_clusters":
            raise ValueError("validation failed")
        return type(
            "Candidate",
            (),
            {
                "dataset": "gov_ai_gold",
                "production_table": production_table,
                "production_table_id": f"western-pivot-452008-a6.gov_ai_gold.{production_table}",
                "staging_table_id": f"western-pivot-452008-a6.gov_ai_gold.{production_table}_staging",
                "staging_table": f"{production_table}_staging",
                "local_row_count": 3,
                "staging_row_count": 3,
                "staging_columns": ["country_code", "year"],
                "load_job_id": "load-x",
            },
        )()

    deps = scheduled_pipeline.Dependencies(
        read_success_metadata_rows=lambda **_: [],
        build_silver_candidate=lambda **_: {
            "manifest_path": str(tmp_path / "silver_manifest.json"),
            "manifest": {"validation_summary": {"row_count": 3}},
            "silver_output_path": str(tmp_path / "silver_output"),
        },
        build_silver_load_plan_fn=lambda **_: {
            "bigquery_write_approved": False,
            "cluster": ["country_code", "indicator", "source"],
            "dataset": "gov_ai_silver",
            "dry_run": True,
            "job_started": False,
            "local_manifest_path": str(tmp_path / "silver_manifest.json"),
            "local_silver_path": str(tmp_path / "silver_output"),
            "location": "asia-southeast1",
            "partition": {"type": "integer_range", "column": "year", "start": 1980, "end": 2031, "interval": 1},
            "project_id": "western-pivot-452008-a6",
            "row_count": 3,
            "source_counts": {"wdi": 1, "gmd": 1, "macro": 1},
            "source_format": "parquet",
            "table": "silver_indicators",
            "table_id": "western-pivot-452008-a6.gov_ai_silver.silver_indicators",
        },
        stage_silver_candidate=lambda **_: {
            "result": {"staging_table_id": "western-pivot-452008-a6.gov_ai_silver.silver_indicators_staging_run_run_1"},
            "validation": {"local_validation": {"row_count": 3}},
        },
        rebuild_warehouse=lambda **_: {
            "silver_preflight": {"year_max": 2025},
            "gold_summary": [{"table_name": "gold_growth_dynamics", "parquet_path": str(tmp_path / "g1.parquet")}],
            "analytics_summary": [{"table_name": "analytics_clusters", "parquet_path": str(tmp_path / "a1.parquet")}],
            "publish_plan": {
                "tables": [
                    {
                        "dataset": "gov_ai_gold",
                        "staging_table": "gold_growth_dynamics_staging_run_run_1",
                        "production_table": "gold_growth_dynamics",
                        "row_count": 3,
                    },
                    {
                        "dataset": "gov_ai_analytics",
                        "staging_table": "analytics_clusters_staging_run_run_1",
                        "production_table": "analytics_clusters",
                        "row_count": 3,
                    },
                ]
            },
        },
        stage_warehouse_candidate=fail_second_candidate,
        run_data_quality_gate=lambda **_: (_ for _ in ()).throw(AssertionError("gate should not run")),
        promote_silver_candidate_fn=lambda **_: (_ for _ in ()).throw(AssertionError("silver promote should not run")),
        promote_warehouse_candidate=lambda **_: (_ for _ in ()).throw(AssertionError("warehouse promote should not run")),
        append_metadata_row=lambda **_: (_ for _ in ()).throw(AssertionError("metadata write should not run")),
        execute_upload_plan_fn=lambda _plan: {"status": "uploaded", "uploaded_count": 1},
        verify_uploaded_source_manifest=lambda **_: {"status": "VERIFIED", "matched": True},
    )
    code, result, metadata = _run(
        tmp_path,
        ["--mode", "execute", "--run-id", "run-1", "--run-date", "2026-05-24", "--allow-network"],
        deps=deps,
    )
    assert code == 1
    assert metadata["status"] == "FAILED"
    assert metadata["last_successful_updated"] is False
    assert result["touched_production_tables"] == []
    assert calls == ["stage_gold_growth_dynamics", "stage_analytics_clusters"]


def test_execute_partial_failed_after_production_mutation_begins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_raw = _prepare_runtime_raw(tmp_path)
    monkeypatch.setenv("CLOUD_WRITE_APPROVED", "true")
    monkeypatch.setenv("BIGQUERY_WRITE_APPROVED", "true")
    monkeypatch.setenv("BIGQUERY_WAREHOUSE_WRITE_APPROVED", "true")
    monkeypatch.setenv("BIGQUERY_OPS_WRITE_APPROVED", "true")
    monkeypatch.setattr(
        scheduled_pipeline,
        "run_acquisition",
        lambda **_: (
            {
                "run_id": "run-1",
                "run_date": "2026-05-24",
                "status": "valid",
                "sources": [
                    {
                        "source_name": "wdi",
                        "combined_fingerprint": "new",
                        "runtime_materialized_path": str((runtime_raw / "worldBank").resolve()),
                        "present_files": ["WDICSV.csv"],
                        "validation_status": "valid",
                    }
                ],
            },
            [],
        ),
    )

    class _Candidate:
        def __init__(self, production_table: str) -> None:
            self.dataset = "gov_ai_gold"
            self.production_table = production_table
            self.production_table_id = f"western-pivot-452008-a6.gov_ai_gold.{production_table}"
            self.staging_table_id = f"western-pivot-452008-a6.gov_ai_gold.{production_table}_staging"
            self.staging_table = f"{production_table}_staging"
            self.local_row_count = 3
            self.staging_row_count = 3
            self.staging_columns = ["country_code", "year"]
            self.load_job_id = "load-x"

    def promote_warehouse(*, candidate: Any, **_kwargs: Any) -> Any:
        if candidate.production_table == "analytics_clusters":
            raise RuntimeError("production copy failed")
        return type(
            "Promoted",
            (),
            {
                "dataset": candidate.dataset,
                "production_table_id": candidate.production_table_id,
                "staging_table_id": candidate.staging_table_id,
            },
        )()

    canonical_tables = _canonical_publish_tables(row_count=3)

    deps = scheduled_pipeline.Dependencies(
        read_success_metadata_rows=lambda **_: [],
        build_silver_candidate=lambda **_: {
            "manifest_path": str(tmp_path / "silver_manifest.json"),
            "manifest": {"validation_summary": {"row_count": 3}},
            "silver_output_path": str(tmp_path / "silver_output"),
        },
        build_silver_load_plan_fn=lambda **_: {
            "bigquery_write_approved": False,
            "cluster": ["country_code", "indicator", "source"],
            "dataset": "gov_ai_silver",
            "dry_run": True,
            "job_started": False,
            "local_manifest_path": str(tmp_path / "silver_manifest.json"),
            "local_silver_path": str(tmp_path / "silver_output"),
            "location": "asia-southeast1",
            "partition": {"type": "integer_range", "column": "year", "start": 1980, "end": 2031, "interval": 1},
            "project_id": "western-pivot-452008-a6",
            "row_count": 3,
            "source_counts": {"wdi": 1, "gmd": 1, "macro": 1},
            "source_format": "parquet",
            "table": "silver_indicators",
            "table_id": "western-pivot-452008-a6.gov_ai_silver.silver_indicators",
        },
        stage_silver_candidate=lambda **_: {
            "result": {"staging_table_id": "western-pivot-452008-a6.gov_ai_silver.silver_indicators_staging_run_run_1"},
            "validation": {"local_validation": {"row_count": 3}},
        },
        rebuild_warehouse=lambda **_: {
            "silver_preflight": {"year_max": 2025},
            "gold_summary": [
                {"table_name": item["production_table"], "parquet_path": str(tmp_path / f"{item['production_table']}.parquet")}
                for item in canonical_tables
                if item["dataset"] == "gov_ai_gold"
            ],
            "analytics_summary": [
                {"table_name": item["production_table"], "parquet_path": str(tmp_path / f"{item['production_table']}.parquet")}
                for item in canonical_tables
                if item["dataset"] == "gov_ai_analytics"
            ],
            "publish_plan": {"tables": canonical_tables},
        },
        stage_warehouse_candidate=lambda *, production_table, **_kwargs: _Candidate(production_table),
        run_data_quality_gate=lambda **_: {"status": "PASSED", "errors": [], "checked_tables": ["silver_indicators"]},
        promote_silver_candidate_fn=lambda **_: {
            "target_table_id": "western-pivot-452008-a6.gov_ai_silver.silver_indicators"
        },
        promote_warehouse_candidate=promote_warehouse,
        recovery_retention_days=lambda *_: 45,
        prepare_recovery_backups_fn=lambda **kwargs: _mock_recovery_ready(
            production_table_ids=list(kwargs["production_table_ids"]),
            retention_days=int(kwargs["retention_days"]),
        ),
        append_metadata_row=lambda **_: (_ for _ in ()).throw(AssertionError("metadata write should not run")),
        execute_upload_plan_fn=lambda _plan: {"status": "uploaded", "uploaded_count": 1},
        verify_uploaded_source_manifest=lambda **_: {"status": "VERIFIED", "matched": True},
    )
    code, result, metadata = _run(
        tmp_path,
        ["--mode", "execute", "--run-id", "run-1", "--run-date", "2026-05-24", "--allow-network"],
        deps=deps,
    )
    assert code == 1
    assert metadata["status"] == "PARTIAL_FAILED"
    assert metadata["last_successful_updated"] is False
    assert metadata["publish_performed"] is False
    assert len(result["touched_production_tables"]) >= 2


def test_execute_verification_mismatch_blocks_bigquery_and_success_append(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_raw = _prepare_runtime_raw(tmp_path)
    monkeypatch.setenv("CLOUD_WRITE_APPROVED", "true")
    monkeypatch.setattr(
        scheduled_pipeline,
        "run_acquisition",
        lambda **_: (
            {
                "run_id": "run-1",
                "run_date": "2026-05-24",
                "status": "valid",
                "sources": [{"source_name": "wdi", "combined_fingerprint": "new", "runtime_materialized_path": str((runtime_raw / "worldBank").resolve()), "present_files": ["WDICSV.csv"], "validation_status": "valid"}],
            },
            [],
        ),
    )
    calls = {"silver_stage": 0, "warehouse_stage": 0, "promote": 0, "metadata_append": 0, "verify": 0}
    deps = scheduled_pipeline.Dependencies(
        read_success_metadata_rows=lambda **_: [],
        execute_upload_plan_fn=lambda _plan: {"status": "uploaded", "uploaded_count": 1},
        verify_uploaded_source_manifest=lambda **_: (calls.__setitem__("verify", calls["verify"] + 1) or {"status": "MISMATCH", "matched": False}),
        stage_silver_candidate=lambda **_: (calls.__setitem__("silver_stage", calls["silver_stage"] + 1) or {}),
        stage_warehouse_candidate=lambda **_: (calls.__setitem__("warehouse_stage", calls["warehouse_stage"] + 1) or {}),
        promote_silver_candidate_fn=lambda **_: (calls.__setitem__("promote", calls["promote"] + 1) or {}),
        promote_warehouse_candidate=lambda **_: (calls.__setitem__("promote", calls["promote"] + 1) or {}),
        append_metadata_row=lambda **_: (calls.__setitem__("metadata_append", calls["metadata_append"] + 1) or {}),
    )
    code, result, metadata = _run(
        tmp_path,
        ["--mode", "execute", "--run-id", "run-1", "--run-date", "2026-05-24", "--allow-network"],
        deps=deps,
    )
    assert code == 1
    assert metadata["status"] == "VALIDATION_FAILED"
    assert metadata["bronze_write_performed"] is True
    assert metadata["cloud_write"] is True
    assert metadata["last_successful_updated"] is False
    assert calls == {"silver_stage": 0, "warehouse_stage": 0, "promote": 0, "metadata_append": 0, "verify": 1}
    assert result["touched_production_tables"] == []


def test_execute_upload_first_object_failure_keeps_cloud_write_false_and_skips_verify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_raw = _prepare_runtime_raw(tmp_path)
    monkeypatch.setenv("CLOUD_WRITE_APPROVED", "true")
    monkeypatch.setattr(
        scheduled_pipeline,
        "run_acquisition",
        lambda **_: (
            {
                "run_id": "run-1",
                "run_date": "2026-05-24",
                "status": "valid",
                "sources": [{"source_name": "wdi", "combined_fingerprint": "new", "runtime_materialized_path": str((runtime_raw / "worldBank").resolve()), "present_files": ["WDICSV.csv"], "validation_status": "valid"}],
            },
            [],
        ),
    )
    calls = {"verify": 0, "silver_stage": 0, "warehouse_stage": 0, "promote": 0, "metadata_append": 0}
    deps = scheduled_pipeline.Dependencies(
        read_success_metadata_rows=lambda **_: [],
        execute_upload_plan_fn=lambda _plan: {
            "status": "FAILED",
            "uploaded_count": 0,
            "cloud_write_performed": False,
            "uploaded_objects": [],
            "failed_object": {"target_gcs_uri": "gs://bucket/path/file-1.txt"},
            "error_message": "upload failed object-1",
        },
        verify_uploaded_source_manifest=lambda **_: (calls.__setitem__("verify", calls["verify"] + 1) or {"status": "VERIFIED"}),
        stage_silver_candidate=lambda **_: (calls.__setitem__("silver_stage", calls["silver_stage"] + 1) or {}),
        stage_warehouse_candidate=lambda **_: (calls.__setitem__("warehouse_stage", calls["warehouse_stage"] + 1) or {}),
        promote_silver_candidate_fn=lambda **_: (calls.__setitem__("promote", calls["promote"] + 1) or {}),
        promote_warehouse_candidate=lambda **_: (calls.__setitem__("promote", calls["promote"] + 1) or {}),
        append_metadata_row=lambda **_: (calls.__setitem__("metadata_append", calls["metadata_append"] + 1) or {}),
    )
    code, result, metadata = _run(
        tmp_path,
        ["--mode", "execute", "--run-id", "run-1", "--run-date", "2026-05-24", "--allow-network"],
        deps=deps,
    )
    assert code == 1
    assert metadata["status"] == "VALIDATION_FAILED"
    assert metadata["bronze_write_performed"] is False
    assert metadata["cloud_write"] is False
    assert metadata["validation_status"] == "FAILED"
    assert metadata["data_quality_status"] == "NOT_EXECUTED"
    assert metadata["last_successful_updated"] is False
    assert calls == {"verify": 0, "silver_stage": 0, "warehouse_stage": 0, "promote": 0, "metadata_append": 0}
    assert result["touched_production_tables"] == []


def test_execute_upload_partial_failure_sets_cloud_write_true_and_skips_verify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_raw = _prepare_runtime_raw(tmp_path)
    monkeypatch.setenv("CLOUD_WRITE_APPROVED", "true")
    monkeypatch.setattr(
        scheduled_pipeline,
        "run_acquisition",
        lambda **_: (
            {
                "run_id": "run-1",
                "run_date": "2026-05-24",
                "status": "valid",
                "sources": [{"source_name": "wdi", "combined_fingerprint": "new", "runtime_materialized_path": str((runtime_raw / "worldBank").resolve()), "present_files": ["WDICSV.csv"], "validation_status": "valid"}],
            },
            [],
        ),
    )
    calls = {"verify": 0, "silver_stage": 0, "warehouse_stage": 0, "promote": 0, "metadata_append": 0}
    deps = scheduled_pipeline.Dependencies(
        read_success_metadata_rows=lambda **_: [],
        execute_upload_plan_fn=lambda _plan: {
            "status": "PARTIAL_FAILED",
            "uploaded_count": 1,
            "cloud_write_performed": True,
            "uploaded_objects": [{"target_gcs_uri": "gs://bucket/path/file-1.txt"}],
            "failed_object": {"target_gcs_uri": "gs://bucket/path/file-2.txt"},
            "error_message": "upload failed object-2",
        },
        verify_uploaded_source_manifest=lambda **_: (calls.__setitem__("verify", calls["verify"] + 1) or {"status": "VERIFIED"}),
        stage_silver_candidate=lambda **_: (calls.__setitem__("silver_stage", calls["silver_stage"] + 1) or {}),
        stage_warehouse_candidate=lambda **_: (calls.__setitem__("warehouse_stage", calls["warehouse_stage"] + 1) or {}),
        promote_silver_candidate_fn=lambda **_: (calls.__setitem__("promote", calls["promote"] + 1) or {}),
        promote_warehouse_candidate=lambda **_: (calls.__setitem__("promote", calls["promote"] + 1) or {}),
        append_metadata_row=lambda **_: (calls.__setitem__("metadata_append", calls["metadata_append"] + 1) or {}),
    )
    code, result, metadata = _run(
        tmp_path,
        ["--mode", "execute", "--run-id", "run-1", "--run-date", "2026-05-24", "--allow-network"],
        deps=deps,
    )
    assert code == 1
    assert metadata["status"] == "VALIDATION_FAILED"
    assert metadata["bronze_write_performed"] is True
    assert metadata["cloud_write"] is True
    assert metadata["validation_status"] == "FAILED"
    assert metadata["data_quality_status"] == "NOT_EXECUTED"
    assert metadata["last_successful_updated"] is False
    assert calls == {"verify": 0, "silver_stage": 0, "warehouse_stage": 0, "promote": 0, "metadata_append": 0}
    assert result["touched_production_tables"] == []


def test_execute_verification_read_failure_blocks_bigquery_and_success_append(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_raw = _prepare_runtime_raw(tmp_path)
    monkeypatch.setenv("CLOUD_WRITE_APPROVED", "true")
    monkeypatch.setattr(
        scheduled_pipeline,
        "run_acquisition",
        lambda **_: (
            {
                "run_id": "run-1",
                "run_date": "2026-05-24",
                "status": "valid",
                "sources": [{"source_name": "wdi", "combined_fingerprint": "new", "runtime_materialized_path": str((runtime_raw / "worldBank").resolve()), "present_files": ["WDICSV.csv"], "validation_status": "valid"}],
            },
            [],
        ),
    )
    deps = scheduled_pipeline.Dependencies(
        read_success_metadata_rows=lambda **_: [],
        execute_upload_plan_fn=lambda _plan: {"status": "uploaded", "uploaded_count": 1},
        verify_uploaded_source_manifest=lambda **_: {"status": "FAILED", "matched": False, "error": "not found"},
        stage_silver_candidate=lambda **_: (_ for _ in ()).throw(AssertionError("silver stage must not run")),
        stage_warehouse_candidate=lambda **_: (_ for _ in ()).throw(AssertionError("warehouse stage must not run")),
        promote_silver_candidate_fn=lambda **_: (_ for _ in ()).throw(AssertionError("silver promote must not run")),
        promote_warehouse_candidate=lambda **_: (_ for _ in ()).throw(AssertionError("warehouse promote must not run")),
        append_metadata_row=lambda **_: (_ for _ in ()).throw(AssertionError("metadata append must not run")),
    )
    code, _result, metadata = _run(
        tmp_path,
        ["--mode", "execute", "--run-id", "run-1", "--run-date", "2026-05-24", "--allow-network"],
        deps=deps,
    )
    assert code == 1
    assert metadata["status"] == "VALIDATION_FAILED"
    assert metadata["bronze_write_performed"] is True
    assert metadata["cloud_write"] is True
    assert metadata["last_successful_updated"] is False


def test_execute_blocks_without_bigquery_write_approval_after_upload_and_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_raw = _prepare_runtime_raw(tmp_path)
    monkeypatch.setenv("CLOUD_WRITE_APPROVED", "true")
    monkeypatch.delenv("BIGQUERY_WRITE_APPROVED", raising=False)
    monkeypatch.setattr(
        scheduled_pipeline,
        "run_acquisition",
        lambda **_: (
            {"run_id": "run-1", "run_date": "2026-05-24", "status": "valid", "sources": [{"source_name": "wdi", "combined_fingerprint": "new", "runtime_materialized_path": str((runtime_raw / "worldBank").resolve()), "present_files": ["WDICSV.csv"], "validation_status": "valid"}]},
            [],
        ),
    )
    calls = {"upload": 0, "verify": 0, "silver_stage": 0, "metadata_append": 0}
    deps = scheduled_pipeline.Dependencies(
        read_success_metadata_rows=lambda **_: [],
        execute_upload_plan_fn=lambda _plan: (calls.__setitem__("upload", calls["upload"] + 1) or {"status": "uploaded", "uploaded_count": 1}),
        verify_uploaded_source_manifest=lambda **_: (calls.__setitem__("verify", calls["verify"] + 1) or {"status": "VERIFIED", "matched": True}),
        stage_silver_candidate=lambda **_: (calls.__setitem__("silver_stage", calls["silver_stage"] + 1) or {}),
        append_metadata_row=lambda **_: (calls.__setitem__("metadata_append", calls["metadata_append"] + 1) or {}),
    )
    code, _result, metadata = _run(
        tmp_path,
        ["--mode", "execute", "--run-id", "run-1", "--run-date", "2026-05-24", "--allow-network"],
        deps=deps,
    )
    assert code == 0
    assert metadata["status"] == "BLOCKED_APPROVAL_REQUIRED"
    assert calls["upload"] == 1
    assert calls["verify"] == 1
    assert calls["silver_stage"] == 0
    assert calls["metadata_append"] == 0


def test_execute_blocks_without_bigquery_warehouse_write_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_raw = _prepare_runtime_raw(tmp_path)
    monkeypatch.setenv("CLOUD_WRITE_APPROVED", "true")
    monkeypatch.setenv("BIGQUERY_WRITE_APPROVED", "true")
    monkeypatch.delenv("BIGQUERY_WAREHOUSE_WRITE_APPROVED", raising=False)
    monkeypatch.setattr(
        scheduled_pipeline,
        "run_acquisition",
        lambda **_: (
            {"run_id": "run-1", "run_date": "2026-05-24", "status": "valid", "sources": [{"source_name": "wdi", "combined_fingerprint": "new", "runtime_materialized_path": str((runtime_raw / "worldBank").resolve()), "present_files": ["WDICSV.csv"], "validation_status": "valid"}]},
            [],
        ),
    )
    calls = {"silver_stage": 0, "warehouse_stage": 0, "promote": 0, "metadata_append": 0}
    deps = scheduled_pipeline.Dependencies(
        read_success_metadata_rows=lambda **_: [],
        execute_upload_plan_fn=lambda _plan: {"status": "uploaded", "uploaded_count": 1},
        verify_uploaded_source_manifest=lambda **_: {"status": "VERIFIED", "matched": True},
        build_silver_candidate=lambda **_: {"manifest_path": str(tmp_path / "silver_manifest.json"), "manifest": {"validation_summary": {"row_count": 3}}, "silver_output_path": str(tmp_path / "silver_output")},
        build_silver_load_plan_fn=lambda **_: {"table_id": "x"},
        stage_silver_candidate=lambda **_: (calls.__setitem__("silver_stage", calls["silver_stage"] + 1) or {"result": {"staging_table_id": "p.d.t"}, "validation": {"local_validation": {"row_count": 3}}}),
        rebuild_warehouse=lambda **_: (calls.__setitem__("warehouse_stage", calls["warehouse_stage"] + 1) or {"silver_preflight": {"year_max": 2025}, "gold_summary": [], "analytics_summary": [], "publish_plan": {"tables": []}}),
        promote_silver_candidate_fn=lambda **_: (calls.__setitem__("promote", calls["promote"] + 1) or {}),
        promote_warehouse_candidate=lambda **_: (calls.__setitem__("promote", calls["promote"] + 1) or {}),
        append_metadata_row=lambda **_: (calls.__setitem__("metadata_append", calls["metadata_append"] + 1) or {}),
    )
    code, _result, metadata = _run(
        tmp_path,
        ["--mode", "execute", "--run-id", "run-1", "--run-date", "2026-05-24", "--allow-network"],
        deps=deps,
    )
    assert code == 0
    assert metadata["status"] == "BLOCKED_APPROVAL_REQUIRED"
    assert calls["silver_stage"] == 1
    assert calls["promote"] == 0
    assert calls["metadata_append"] == 0


def test_execute_prepares_recovery_backups_for_all_production_tables_before_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_raw = _prepare_runtime_raw(tmp_path)
    monkeypatch.setenv("CLOUD_WRITE_APPROVED", "true")
    monkeypatch.setenv("BIGQUERY_WRITE_APPROVED", "true")
    monkeypatch.setenv("BIGQUERY_WAREHOUSE_WRITE_APPROVED", "true")
    monkeypatch.setenv("BIGQUERY_OPS_WRITE_APPROVED", "true")
    monkeypatch.setenv("RECOVERY_TABLE_RETENTION_DAYS", "45")
    monkeypatch.setattr(
        scheduled_pipeline,
        "run_acquisition",
        lambda **_: (
            {
                "run_id": "run-1",
                "run_date": "2026-05-24",
                "status": "valid",
                "sources": [
                    {
                        "source_name": "wdi",
                        "combined_fingerprint": "new",
                        "runtime_materialized_path": str((runtime_raw / "worldBank").resolve()),
                        "present_files": ["WDICSV.csv"],
                        "validation_status": "valid",
                    }
                ],
            },
            [],
        ),
    )

    call_order: list[str] = []
    captured: dict[str, Any] = {}

    class _Candidate:
        def __init__(self, dataset: str, table_name: str) -> None:
            self.dataset = dataset
            self.production_table = table_name
            self.production_table_id = f"western-pivot-452008-a6.{dataset}.{table_name}"
            self.staging_table_id = f"{self.production_table_id}_staging"
            self.staging_table = f"{table_name}_staging"
            self.local_row_count = 1
            self.staging_row_count = 1
            self.staging_columns = ["country_code", "year"]
            self.load_job_id = f"load-{table_name}"

    publish_tables = [
        {"dataset": "gov_ai_gold", "production_table": "gold_growth_dynamics", "staging_table": "gold_growth_dynamics_staging", "row_count": 1},
        {"dataset": "gov_ai_gold", "production_table": "gold_fiscal_monetary", "staging_table": "gold_fiscal_monetary_staging", "row_count": 1},
        {"dataset": "gov_ai_gold", "production_table": "gold_crisis_risk", "staging_table": "gold_crisis_risk_staging", "row_count": 1},
        {"dataset": "gov_ai_gold", "production_table": "gold_social_welfare", "staging_table": "gold_social_welfare_staging", "row_count": 1},
        {"dataset": "gov_ai_gold", "production_table": "gold_structural_composition", "staging_table": "gold_structural_composition_staging", "row_count": 1},
        {"dataset": "gov_ai_analytics", "production_table": "analytics_gold_growth_dynamics", "staging_table": "analytics_gold_growth_dynamics_staging", "row_count": 1},
        {"dataset": "gov_ai_analytics", "production_table": "analytics_gold_fiscal_monetary", "staging_table": "analytics_gold_fiscal_monetary_staging", "row_count": 1},
        {"dataset": "gov_ai_analytics", "production_table": "analytics_gold_crisis_risk", "staging_table": "analytics_gold_crisis_risk_staging", "row_count": 1},
        {"dataset": "gov_ai_analytics", "production_table": "analytics_gold_social_welfare", "staging_table": "analytics_gold_social_welfare_staging", "row_count": 1},
        {"dataset": "gov_ai_analytics", "production_table": "analytics_gold_structural_composition", "staging_table": "analytics_gold_structural_composition_staging", "row_count": 1},
        {"dataset": "gov_ai_analytics", "production_table": "analytics_clusters", "staging_table": "analytics_clusters_staging", "row_count": 1},
    ]

    deps = scheduled_pipeline.Dependencies(
        read_success_metadata_rows=lambda **_: [],
        execute_upload_plan_fn=lambda _plan: {"status": "uploaded", "uploaded_count": 1},
        verify_uploaded_source_manifest=lambda **_: {"status": "VERIFIED", "matched": True},
        build_silver_candidate=lambda **_: {"manifest_path": str(tmp_path / "silver_manifest.json"), "manifest": {"validation_summary": {"row_count": 1}}, "silver_output_path": str(tmp_path / "silver_output")},
        build_silver_load_plan_fn=lambda **_: {"table_id": "x"},
        stage_silver_candidate=lambda **_: {"result": {"staging_table_id": "western-pivot-452008-a6.gov_ai_silver.silver_indicators_staging_run_run_1"}, "validation": {"local_validation": {"row_count": 1}}},
        rebuild_warehouse=lambda **_: {
            "silver_preflight": {"year_max": 2025},
            "gold_summary": [{"table_name": item["production_table"], "parquet_path": str(tmp_path / f"{item['production_table']}.parquet")} for item in publish_tables if item["dataset"] == "gov_ai_gold"],
            "analytics_summary": [{"table_name": item["production_table"], "parquet_path": str(tmp_path / f"{item['production_table']}.parquet")} for item in publish_tables if item["dataset"] == "gov_ai_analytics"],
            "publish_plan": {"tables": publish_tables},
        },
        stage_warehouse_candidate=lambda *, dataset, production_table, **_kwargs: _Candidate(dataset, production_table),
        run_data_quality_gate=lambda **_: {"status": "PASSED", "errors": [], "checked_tables": ["silver_indicators"]},
        prepare_recovery_backups_fn=lambda **kwargs: (
            captured.update({"production_table_ids": kwargs["production_table_ids"], "retention_days": kwargs["retention_days"]})
            or call_order.append("recovery")
            or {"status": "RECOVERY_READY", "retention_days": kwargs["retention_days"], "backups": [{"production_table_id": table_id, "recovery_table_id": table_id + "_recovery"} for table_id in kwargs["production_table_ids"]]}
        ),
        promote_silver_candidate_fn=lambda **_: (call_order.append("promote_silver") or {"target_table_id": "western-pivot-452008-a6.gov_ai_silver.silver_indicators"}),
        promote_warehouse_candidate=lambda *, candidate, **_kwargs: (
            call_order.append(f"promote_{candidate.production_table}")
            or type("P", (), {"dataset": candidate.dataset, "production_table_id": candidate.production_table_id, "staging_table_id": candidate.staging_table_id})()
        ),
        append_metadata_row=lambda **_: {"table_id": "western-pivot-452008-a6.gov_ai_ops.pipeline_run_metadata"},
    )
    code, _result, metadata = _run(
        tmp_path,
        ["--mode", "execute", "--run-id", "run-1", "--run-date", "2026-05-24", "--allow-network"],
        deps=deps,
    )
    assert code == 0
    assert metadata["status"] == "SUCCESS"
    assert captured["production_table_ids"] == PRODUCTION_TABLE_ORDER
    assert captured["retention_days"] == 45
    assert call_order.index("recovery") < call_order.index("promote_silver")


def test_execute_recovery_collision_blocks_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_raw = _prepare_runtime_raw(tmp_path)
    monkeypatch.setenv("CLOUD_WRITE_APPROVED", "true")
    monkeypatch.setenv("BIGQUERY_WRITE_APPROVED", "true")
    monkeypatch.setenv("BIGQUERY_WAREHOUSE_WRITE_APPROVED", "true")
    monkeypatch.setenv("BIGQUERY_OPS_WRITE_APPROVED", "true")
    monkeypatch.setattr(
        scheduled_pipeline,
        "run_acquisition",
        lambda **_: (
            {
                "run_id": "run-1",
                "run_date": "2026-05-24",
                "status": "valid",
                "sources": [{"source_name": "wdi", "combined_fingerprint": "new", "runtime_materialized_path": str((runtime_raw / "worldBank").resolve()), "present_files": ["WDICSV.csv"], "validation_status": "valid"}],
            },
            [],
        ),
    )
    calls = {"promote": 0}
    deps = scheduled_pipeline.Dependencies(
        read_success_metadata_rows=lambda **_: [],
        execute_upload_plan_fn=lambda _plan: {"status": "uploaded", "uploaded_count": 1},
        verify_uploaded_source_manifest=lambda **_: {"status": "VERIFIED", "matched": True},
        build_silver_candidate=lambda **_: {"manifest_path": str(tmp_path / "silver_manifest.json"), "manifest": {"validation_summary": {"row_count": 1}}, "silver_output_path": str(tmp_path / "silver_output")},
        build_silver_load_plan_fn=lambda **_: {"table_id": "x"},
        stage_silver_candidate=lambda **_: {"result": {"staging_table_id": "western-pivot-452008-a6.gov_ai_silver.silver_indicators_staging_run_run_1"}, "validation": {"local_validation": {"row_count": 1}}},
        rebuild_warehouse=lambda **_: {
            "silver_preflight": {"year_max": 2025},
            "gold_summary": [{"table_name": "gold_growth_dynamics", "parquet_path": str(tmp_path / "g1.parquet")}],
            "analytics_summary": [{"table_name": "analytics_clusters", "parquet_path": str(tmp_path / "a1.parquet")}],
            "publish_plan": {"tables": [{"dataset": "gov_ai_gold", "production_table": "gold_growth_dynamics", "staging_table": "gold_growth_dynamics_staging", "row_count": 1}, {"dataset": "gov_ai_analytics", "production_table": "analytics_clusters", "staging_table": "analytics_clusters_staging", "row_count": 1}]},
        },
        stage_warehouse_candidate=lambda *, dataset, production_table, **_kwargs: type("C", (), {"dataset": dataset, "production_table": production_table, "production_table_id": f"western-pivot-452008-a6.{dataset}.{production_table}", "staging_table_id": "x", "staging_table": "x", "local_row_count": 1, "staging_row_count": 1, "staging_columns": ["country_code", "year"], "load_job_id": "j1"})(),
        run_data_quality_gate=lambda **_: {"status": "PASSED", "errors": [], "checked_tables": ["silver_indicators"]},
        prepare_recovery_backups_fn=lambda **_: (_ for _ in ()).throw(scheduled_pipeline.RecoveryCollisionError("collision")),
        promote_silver_candidate_fn=lambda **_: (calls.__setitem__("promote", calls["promote"] + 1) or {}),
        promote_warehouse_candidate=lambda **_: (calls.__setitem__("promote", calls["promote"] + 1) or {}),
    )
    code, _result, metadata = _run(
        tmp_path,
        ["--mode", "execute", "--run-id", "run-1", "--run-date", "2026-05-24", "--allow-network"],
        deps=deps,
    )
    assert code == 1
    assert metadata["status"] == "FAILED"
    assert calls["promote"] == 0


def _build_execute_deps_with_publish_plan(
    *,
    tmp_path: Path,
    publish_tables: list[dict[str, Any]],
    calls: dict[str, int],
) -> scheduled_pipeline.Dependencies:
    class _Candidate:
        def __init__(self, dataset: str, table_name: str) -> None:
            self.dataset = dataset
            self.production_table = table_name
            self.production_table_id = f"western-pivot-452008-a6.{dataset}.{table_name}"
            self.staging_table_id = f"{self.production_table_id}_staging"
            self.staging_table = f"{table_name}_staging"
            self.local_row_count = 1
            self.staging_row_count = 1
            self.staging_columns = ["country_code", "year"]
            self.load_job_id = f"load-{table_name}"

    return scheduled_pipeline.Dependencies(
        read_success_metadata_rows=lambda **_: [],
        execute_upload_plan_fn=lambda _plan: {"status": "uploaded", "uploaded_count": 1},
        verify_uploaded_source_manifest=lambda **_: {"status": "VERIFIED", "matched": True},
        build_silver_candidate=lambda **_: {
            "manifest_path": str(tmp_path / "silver_manifest.json"),
            "manifest": {"validation_summary": {"row_count": 1}},
            "silver_output_path": str(tmp_path / "silver_output"),
        },
        build_silver_load_plan_fn=lambda **_: {"table_id": "x"},
        stage_silver_candidate=lambda **_: {
            "result": {"staging_table_id": "western-pivot-452008-a6.gov_ai_silver.silver_indicators_staging_run_run_1"},
            "validation": {"local_validation": {"row_count": 1}},
        },
        rebuild_warehouse=lambda **_: {
            "silver_preflight": {"year_max": 2025},
            "gold_summary": [
                {"table_name": item["production_table"], "parquet_path": str(tmp_path / f"{item['production_table']}.parquet")}
                for item in publish_tables
                if item["dataset"] == "gov_ai_gold"
            ],
            "analytics_summary": [
                {"table_name": item["production_table"], "parquet_path": str(tmp_path / f"{item['production_table']}.parquet")}
                for item in publish_tables
                if item["dataset"] == "gov_ai_analytics"
            ],
            "publish_plan": {"tables": publish_tables},
        },
        stage_warehouse_candidate=lambda *, dataset, production_table, **_kwargs: _Candidate(dataset, production_table),
        run_data_quality_gate=lambda **_: {"status": "PASSED", "errors": [], "checked_tables": ["silver_indicators"]},
        prepare_recovery_backups_fn=lambda **kwargs: (
            calls.__setitem__("recovery", calls["recovery"] + 1)
            or {"status": "RECOVERY_READY", "retention_days": kwargs["retention_days"], "backups": []}
        ),
        promote_silver_candidate_fn=lambda **_: (
            calls.__setitem__("promote", calls["promote"] + 1)
            or {"target_table_id": "western-pivot-452008-a6.gov_ai_silver.silver_indicators"}
        ),
        promote_warehouse_candidate=lambda *, candidate, **_kwargs: (
            calls.__setitem__("promote", calls["promote"] + 1)
            or type("P", (), {"dataset": candidate.dataset, "production_table_id": candidate.production_table_id, "staging_table_id": candidate.staging_table_id})()
        ),
        append_metadata_row=lambda **_: {"table_id": "western-pivot-452008-a6.gov_ai_ops.pipeline_run_metadata"},
    )


@pytest.mark.parametrize(
    "publish_tables",
    [
        PRODUCTION_TABLE_ORDER[2:],
        [
            {"dataset": "gov_ai_gold", "production_table": "gold_growth_dynamics", "staging_table": "gold_growth_dynamics_staging", "row_count": 1},
            {"dataset": "gov_ai_gold", "production_table": "gold_growth_dynamics", "staging_table": "gold_growth_dynamics_staging_dup", "row_count": 1},
            *[
                {"dataset": "gov_ai_gold", "production_table": "gold_fiscal_monetary", "staging_table": "gold_fiscal_monetary_staging", "row_count": 1},
                {"dataset": "gov_ai_gold", "production_table": "gold_crisis_risk", "staging_table": "gold_crisis_risk_staging", "row_count": 1},
                {"dataset": "gov_ai_gold", "production_table": "gold_social_welfare", "staging_table": "gold_social_welfare_staging", "row_count": 1},
                {"dataset": "gov_ai_gold", "production_table": "gold_structural_composition", "staging_table": "gold_structural_composition_staging", "row_count": 1},
                {"dataset": "gov_ai_analytics", "production_table": "analytics_gold_growth_dynamics", "staging_table": "analytics_gold_growth_dynamics_staging", "row_count": 1},
                {"dataset": "gov_ai_analytics", "production_table": "analytics_gold_fiscal_monetary", "staging_table": "analytics_gold_fiscal_monetary_staging", "row_count": 1},
                {"dataset": "gov_ai_analytics", "production_table": "analytics_gold_crisis_risk", "staging_table": "analytics_gold_crisis_risk_staging", "row_count": 1},
                {"dataset": "gov_ai_analytics", "production_table": "analytics_gold_social_welfare", "staging_table": "analytics_gold_social_welfare_staging", "row_count": 1},
                {"dataset": "gov_ai_analytics", "production_table": "analytics_gold_structural_composition", "staging_table": "analytics_gold_structural_composition_staging", "row_count": 1},
                {"dataset": "gov_ai_analytics", "production_table": "analytics_clusters", "staging_table": "analytics_clusters_staging", "row_count": 1},
            ],
        ],
        [
            {"dataset": "gov_ai_gold", "production_table": "gold_fiscal_monetary", "staging_table": "gold_fiscal_monetary_staging", "row_count": 1},
            {"dataset": "gov_ai_gold", "production_table": "gold_growth_dynamics", "staging_table": "gold_growth_dynamics_staging", "row_count": 1},
            {"dataset": "gov_ai_gold", "production_table": "gold_crisis_risk", "staging_table": "gold_crisis_risk_staging", "row_count": 1},
            {"dataset": "gov_ai_gold", "production_table": "gold_social_welfare", "staging_table": "gold_social_welfare_staging", "row_count": 1},
            {"dataset": "gov_ai_gold", "production_table": "gold_structural_composition", "staging_table": "gold_structural_composition_staging", "row_count": 1},
            {"dataset": "gov_ai_analytics", "production_table": "analytics_gold_growth_dynamics", "staging_table": "analytics_gold_growth_dynamics_staging", "row_count": 1},
            {"dataset": "gov_ai_analytics", "production_table": "analytics_gold_fiscal_monetary", "staging_table": "analytics_gold_fiscal_monetary_staging", "row_count": 1},
            {"dataset": "gov_ai_analytics", "production_table": "analytics_gold_crisis_risk", "staging_table": "analytics_gold_crisis_risk_staging", "row_count": 1},
            {"dataset": "gov_ai_analytics", "production_table": "analytics_gold_social_welfare", "staging_table": "analytics_gold_social_welfare_staging", "row_count": 1},
            {"dataset": "gov_ai_analytics", "production_table": "analytics_gold_structural_composition", "staging_table": "analytics_gold_structural_composition_staging", "row_count": 1},
            {"dataset": "gov_ai_analytics", "production_table": "analytics_clusters", "staging_table": "analytics_clusters_staging", "row_count": 1},
        ],
    ],
)
def test_execute_requires_exact_12_canonical_production_targets_before_recovery_and_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, publish_tables: list[Any]
) -> None:
    runtime_raw = _prepare_runtime_raw(tmp_path)
    monkeypatch.setenv("CLOUD_WRITE_APPROVED", "true")
    monkeypatch.setenv("BIGQUERY_WRITE_APPROVED", "true")
    monkeypatch.setenv("BIGQUERY_WAREHOUSE_WRITE_APPROVED", "true")
    monkeypatch.setenv("BIGQUERY_OPS_WRITE_APPROVED", "true")
    monkeypatch.setattr(
        scheduled_pipeline,
        "run_acquisition",
        lambda **_: (
            {
                "run_id": "run-1",
                "run_date": "2026-05-24",
                "status": "valid",
                "sources": [
                    {
                        "source_name": "wdi",
                        "combined_fingerprint": "new",
                        "runtime_materialized_path": str((runtime_raw / "worldBank").resolve()),
                        "present_files": ["WDICSV.csv"],
                        "validation_status": "valid",
                    }
                ],
            },
            [],
        ),
    )
    calls = {"recovery": 0, "promote": 0}
    if publish_tables and isinstance(publish_tables[0], str):
        normalized_publish_tables = []
    else:
        normalized_publish_tables = publish_tables
    deps = _build_execute_deps_with_publish_plan(
        tmp_path=tmp_path,
        publish_tables=normalized_publish_tables,
        calls=calls,
    )
    code, _result, metadata = _run(
        tmp_path,
        ["--mode", "execute", "--run-id", "run-1", "--run-date", "2026-05-24", "--allow-network"],
        deps=deps,
    )
    assert code == 1
    assert metadata["status"] == "FAILED"
    assert metadata["error_message"] == (
        "production_table_order_mismatch: expected exactly all canonical scheduled production targets"
    )
    assert calls["recovery"] == 0
    assert calls["promote"] == 0


def test_execute_metadata_append_failure_after_promotion_triggers_restore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_raw = _prepare_runtime_raw(tmp_path)
    monkeypatch.setenv("CLOUD_WRITE_APPROVED", "true")
    monkeypatch.setenv("BIGQUERY_WRITE_APPROVED", "true")
    monkeypatch.setenv("BIGQUERY_WAREHOUSE_WRITE_APPROVED", "true")
    monkeypatch.setenv("BIGQUERY_OPS_WRITE_APPROVED", "true")
    monkeypatch.setattr(
        scheduled_pipeline,
        "run_acquisition",
        lambda **_: (
            {
                "run_id": "run-1",
                "run_date": "2026-05-24",
                "status": "valid",
                "sources": [{"source_name": "wdi", "combined_fingerprint": "new", "runtime_materialized_path": str((runtime_raw / "worldBank").resolve()), "present_files": ["WDICSV.csv"], "validation_status": "valid"}],
            },
            [],
        ),
    )
    restore_calls: list[dict[str, Any]] = []

    class _Candidate:
        def __init__(self, table_name: str) -> None:
            self.dataset = "gov_ai_gold"
            self.production_table = table_name
            self.production_table_id = f"western-pivot-452008-a6.gov_ai_gold.{table_name}"
            self.staging_table_id = "x"
            self.staging_table = "x"
            self.local_row_count = 1
            self.staging_row_count = 1
            self.staging_columns = ["country_code", "year"]
            self.load_job_id = "j1"

    canonical_tables = _canonical_publish_tables(row_count=1)

    deps = scheduled_pipeline.Dependencies(
        read_success_metadata_rows=lambda **_: [],
        execute_upload_plan_fn=lambda _plan: {"status": "uploaded", "uploaded_count": 1},
        verify_uploaded_source_manifest=lambda **_: {"status": "VERIFIED", "matched": True},
        build_silver_candidate=lambda **_: {"manifest_path": str(tmp_path / "silver_manifest.json"), "manifest": {"validation_summary": {"row_count": 1}}, "silver_output_path": str(tmp_path / "silver_output")},
        build_silver_load_plan_fn=lambda **_: {"table_id": "x"},
        stage_silver_candidate=lambda **_: {"result": {"staging_table_id": "western-pivot-452008-a6.gov_ai_silver.silver_indicators_staging_run_run_1"}, "validation": {"local_validation": {"row_count": 1}}},
        rebuild_warehouse=lambda **_: {
            "silver_preflight": {"year_max": 2025},
            "gold_summary": [
                {"table_name": item["production_table"], "parquet_path": str(tmp_path / f"{item['production_table']}.parquet")}
                for item in canonical_tables
                if item["dataset"] == "gov_ai_gold"
            ],
            "analytics_summary": [
                {"table_name": item["production_table"], "parquet_path": str(tmp_path / f"{item['production_table']}.parquet")}
                for item in canonical_tables
                if item["dataset"] == "gov_ai_analytics"
            ],
            "publish_plan": {"tables": canonical_tables},
        },
        stage_warehouse_candidate=lambda *, production_table, **_kwargs: _Candidate(production_table),
        run_data_quality_gate=lambda **_: {"status": "PASSED", "errors": [], "checked_tables": ["silver_indicators"]},
        prepare_recovery_backups_fn=lambda **kwargs: {
            "status": "RECOVERY_READY",
            "retention_days": kwargs["retention_days"],
            "backups": [
                {"production_table_id": table_id, "recovery_table_id": table_id + "_recovery"}
                for table_id in kwargs["production_table_ids"]
            ],
        },
        promote_silver_candidate_fn=lambda **_: {"target_table_id": "western-pivot-452008-a6.gov_ai_silver.silver_indicators"},
        promote_warehouse_candidate=lambda *, candidate, **_kwargs: type("P", (), {"dataset": candidate.dataset, "production_table_id": candidate.production_table_id, "staging_table_id": candidate.staging_table_id})(),
        append_metadata_row=lambda **_: (_ for _ in ()).throw(RuntimeError("metadata write failed")),
        restore_production_tables_fn=lambda **kwargs: (restore_calls.append(kwargs) or {"status": "RESTORE_SUCCEEDED", "restored": [{"production_table_id": table_id} for table_id in kwargs["touched_production_tables"]], "failed": []}),
    )
    code, _result, metadata = _run(
        tmp_path,
        ["--mode", "execute", "--run-id", "run-1", "--run-date", "2026-05-24", "--allow-network"],
        deps=deps,
    )
    assert code == 1
    assert metadata["status"] == "PARTIAL_FAILED"
    assert metadata["last_successful_updated"] is False
    assert restore_calls
    assert len(restore_calls[0]["touched_production_tables"]) >= 2


def test_execute_blocks_without_bigquery_ops_write_approval_before_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_raw = _prepare_runtime_raw(tmp_path)
    monkeypatch.setenv("CLOUD_WRITE_APPROVED", "true")
    monkeypatch.setenv("BIGQUERY_WRITE_APPROVED", "true")
    monkeypatch.setenv("BIGQUERY_WAREHOUSE_WRITE_APPROVED", "true")
    monkeypatch.delenv("BIGQUERY_OPS_WRITE_APPROVED", raising=False)
    monkeypatch.setattr(
        scheduled_pipeline,
        "run_acquisition",
        lambda **_: (
            {"run_id": "run-1", "run_date": "2026-05-24", "status": "valid", "sources": [{"source_name": "wdi", "combined_fingerprint": "new", "runtime_materialized_path": str((runtime_raw / "worldBank").resolve()), "present_files": ["WDICSV.csv"], "validation_status": "valid"}]},
            [],
        ),
    )
    calls = {"promote": 0, "metadata_append": 0}
    candidate = type(
        "Candidate",
        (),
        {
            "dataset": "gov_ai_gold",
            "production_table": "gold_growth_dynamics",
            "production_table_id": "p.g.t",
            "staging_table_id": "p.g.ts",
            "staging_table": "gold_growth_dynamics_staging",
            "local_row_count": 1,
            "staging_row_count": 1,
            "staging_columns": ["country_code", "year"],
            "load_job_id": "j1",
        },
    )()
    deps = scheduled_pipeline.Dependencies(
        read_success_metadata_rows=lambda **_: [],
        execute_upload_plan_fn=lambda _plan: {"status": "uploaded", "uploaded_count": 1},
        verify_uploaded_source_manifest=lambda **_: {"status": "VERIFIED", "matched": True},
        build_silver_candidate=lambda **_: {"manifest_path": str(tmp_path / "silver_manifest.json"), "manifest": {"validation_summary": {"row_count": 1}}, "silver_output_path": str(tmp_path / "silver_output")},
        build_silver_load_plan_fn=lambda **_: {"table_id": "x"},
        stage_silver_candidate=lambda **_: {"result": {"staging_table_id": "p.d.t"}, "validation": {"local_validation": {"row_count": 1}}},
        rebuild_warehouse=lambda **_: {"silver_preflight": {"year_max": 2025}, "gold_summary": [{"table_name": "gold_growth_dynamics", "parquet_path": str(tmp_path / "g1.parquet")}], "analytics_summary": [], "publish_plan": {"tables": [{"dataset": "gov_ai_gold", "staging_table": "gold_growth_dynamics_staging", "production_table": "gold_growth_dynamics", "row_count": 1}]}},
        stage_warehouse_candidate=lambda **_: candidate,
        run_data_quality_gate=lambda **_: {"status": "PASSED", "errors": [], "checked_tables": ["silver_indicators", "gold_growth_dynamics"]},
        promote_silver_candidate_fn=lambda **_: (calls.__setitem__("promote", calls["promote"] + 1) or {}),
        promote_warehouse_candidate=lambda **_: (calls.__setitem__("promote", calls["promote"] + 1) or {}),
        append_metadata_row=lambda **_: (calls.__setitem__("metadata_append", calls["metadata_append"] + 1) or {}),
    )
    code, _result, metadata = _run(
        tmp_path,
        ["--mode", "execute", "--run-id", "run-1", "--run-date", "2026-05-24", "--allow-network"],
        deps=deps,
    )
    assert code == 0
    assert metadata["status"] == "BLOCKED_APPROVAL_REQUIRED"
    assert calls["promote"] == 0
    assert calls["metadata_append"] == 0


def test_execute_failure_records_typed_keyerror_and_failed_step_for_silver_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_raw = _prepare_runtime_raw(tmp_path)
    monkeypatch.setenv("CLOUD_WRITE_APPROVED", "true")
    monkeypatch.setenv("BIGQUERY_WRITE_APPROVED", "true")
    monkeypatch.setattr(
        scheduled_pipeline,
        "run_acquisition",
        lambda **_: (
            {
                "run_id": "run-1",
                "run_date": "2026-05-24",
                "status": "valid",
                "sources": [
                    {
                        "source_name": "wdi",
                        "combined_fingerprint": "new",
                        "runtime_materialized_path": str((runtime_raw / "worldBank").resolve()),
                        "present_files": ["WDICSV.csv"],
                        "validation_status": "valid",
                    }
                ],
            },
            [],
        ),
    )
    deps = scheduled_pipeline.Dependencies(
        read_success_metadata_rows=lambda **_: [],
        execute_upload_plan_fn=lambda _plan: {"status": "UPLOADED", "uploaded_count": 1},
        verify_uploaded_source_manifest=lambda **_: {"status": "VERIFIED", "matched": True},
        build_silver_candidate=lambda **_: {
            "manifest_path": str(tmp_path / "silver_manifest.json"),
            "manifest": {"validation_summary": {"row_count": 1}},
            "silver_output_path": str(tmp_path / "silver_output"),
        },
        build_silver_load_plan_fn=lambda **_: {"table_id": "x"},
        stage_silver_candidate=lambda **_: (_ for _ in ()).throw(KeyError(3)),
    )
    code, result, metadata = _run(
        tmp_path,
        ["--mode", "execute", "--run-id", "run-1", "--run-date", "2026-05-24", "--allow-network"],
        deps=deps,
    )
    assert code == 1
    assert metadata["status"] == "FAILED"
    assert metadata["failed_step"] == "stage_validate_silver_candidate"
    assert metadata["exception_type"] == "KeyError"
    assert "KeyError(3)" in metadata["error_message"]
    assert metadata["traceback_tail"]
    assert result["failed_step"] == "stage_validate_silver_candidate"
    assert result["exception_type"] == "KeyError"


def test_execute_failure_records_typed_keyerror_and_failed_step_for_warehouse_rebuild(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_raw = _prepare_runtime_raw(tmp_path)
    monkeypatch.setenv("CLOUD_WRITE_APPROVED", "true")
    monkeypatch.setenv("BIGQUERY_WRITE_APPROVED", "true")
    monkeypatch.setenv("BIGQUERY_WAREHOUSE_WRITE_APPROVED", "true")
    monkeypatch.setattr(
        scheduled_pipeline,
        "run_acquisition",
        lambda **_: (
            {
                "run_id": "run-1",
                "run_date": "2026-05-24",
                "status": "valid",
                "sources": [
                    {
                        "source_name": "wdi",
                        "combined_fingerprint": "new",
                        "runtime_materialized_path": str((runtime_raw / "worldBank").resolve()),
                        "present_files": ["WDICSV.csv"],
                        "validation_status": "valid",
                    }
                ],
            },
            [],
        ),
    )
    deps = scheduled_pipeline.Dependencies(
        read_success_metadata_rows=lambda **_: [],
        execute_upload_plan_fn=lambda _plan: {"status": "UPLOADED", "uploaded_count": 1},
        verify_uploaded_source_manifest=lambda **_: {"status": "VERIFIED", "matched": True},
        build_silver_candidate=lambda **_: {
            "manifest_path": str(tmp_path / "silver_manifest.json"),
            "manifest": {"validation_summary": {"row_count": 1}},
            "silver_output_path": str(tmp_path / "silver_output"),
        },
        build_silver_load_plan_fn=lambda **_: {"table_id": "x"},
        stage_silver_candidate=lambda **_: {
            "result": {"staging_table_id": "western-pivot-452008-a6.gov_ai_silver.silver_indicators_staging_run_run_1"},
            "validation": {"local_validation": {"row_count": 1}},
        },
        rebuild_warehouse=lambda **_: (_ for _ in ()).throw(KeyError(3)),
    )
    code, result, metadata = _run(
        tmp_path,
        ["--mode", "execute", "--run-id", "run-1", "--run-date", "2026-05-24", "--allow-network"],
        deps=deps,
    )
    assert code == 1
    assert metadata["status"] == "FAILED"
    assert metadata["failed_step"] == "build_gold_analytics_candidates"
    assert metadata["exception_type"] == "KeyError"
    assert "KeyError(3)" in metadata["error_message"]
    assert metadata["traceback_tail"]
    assert result["failed_step"] == "build_gold_analytics_candidates"
    assert result["exception_type"] == "KeyError"
