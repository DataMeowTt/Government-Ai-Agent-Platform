from __future__ import annotations

import json
import sys
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[3]
    scripts_dir = repo_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import workflow_scheduler_plan as module

    return module


def test_plan_validates_successfully_and_uses_bigquery_direct_path() -> None:
    module = _load_module()
    plan = module.build_plan()
    validation = module.validate_plan(plan)
    assert validation["status"] == "PASS"
    assert [step["step"] for step in plan["workflow"]["orchestration_order"]] == [
        "initialize_run",
        "fetch_official_sources_and_decide_change",
        "branch_unchanged_skip_or_changed_continue",
        "persist_bronze_and_manifests_if_changed",
        "build_and_validate_silver_candidate",
        "build_and_validate_gold_analytics_candidates",
        "run_data_quality_gate",
        "publish_bigquery_production_if_valid",
        "record_success_freshness",
        "backend_freshness_smoke",
    ]
    assert plan["workflow"]["main_path"] == "bigquery_direct"
    assert plan["workflow"]["branch_semantics"]["unchanged"]["terminal_status"] == "SKIPPED_UNCHANGED"
    assert plan["workflow"]["branch_semantics"]["unchanged"]["warehouse_publish_performed"] is False
    assert plan["workflow"]["branch_semantics"]["unchanged"]["last_successful_updated"] is False
    assert plan["required_path_constraints"]["main_path"] == "bigquery_direct"
    assert plan["required_path_constraints"]["postgres_required_in_main_path"] is False
    assert plan["required_path_constraints"]["analytics_worker_postgres_required"] is False


def test_unchanged_branch_semantics_and_scheduler_paused_monthly_utc() -> None:
    module = _load_module()
    plan = module.build_plan()
    branch = plan["workflow"]["orchestration_order"][2]["branch"]["unchanged"]
    assert branch["status"] == "SKIPPED_UNCHANGED"
    assert branch["publish"] is False
    assert branch["warehouse_publish_performed"] is False
    assert branch["last_successful_updated"] is False
    scheduler = plan["scheduler"]
    assert scheduler["schedule"] == "0 2 5 * *"
    assert scheduler["time_zone"] == "UTC"
    assert scheduler["paused"] is True
    assert scheduler["state"] == "PAUSED"
    assert scheduler["activation_requires_later_approval"] is True


def test_yaml_format_output_contains_required_steps_and_scheduler_fields(capsys) -> None:
    module = _load_module()
    assert module.main(["--format", "yaml"]) == 0
    output = capsys.readouterr().out
    for token in [
        "initialize_run",
        "fetch_official_sources_and_decide_change",
        "branch_unchanged_skip_or_changed_continue",
        "persist_bronze_and_manifests_if_changed",
        "build_and_validate_silver_candidate",
        "build_and_validate_gold_analytics_candidates",
        "run_data_quality_gate",
        "publish_bigquery_production_if_valid",
        "record_success_freshness",
        "backend_freshness_smoke",
        "0 2 5 * *",
        "UTC",
        "PAUSED",
        "activation_requires_later_approval",
    ]:
        assert token in output


def test_template_outputs_are_cloud_command_free() -> None:
    module = _load_module()
    plan = module.build_plan()
    assert module.validate_no_cloud_command_text(plan["workflow"]["yaml_template"]) == []
    assert module.validate_no_cloud_command_text(plan["scheduler"]["yaml_template"]) == []


def test_validate_plan_rejects_command_text_in_templates() -> None:
    module = _load_module()
    plan = module.build_plan()
    plan["scheduler"]["yaml_template"] = plan["scheduler"]["yaml_template"] + "\ngcloud run jobs execute bad\n"
    validation = module.validate_plan(plan)
    assert validation["status"] == "FAIL"
    assert any("scheduler_yaml_template" in error for error in validation["errors"])


def test_cloud_command_validator_rejects_malicious_strings() -> None:
    module = _load_module()
    malicious = {
        "gcloud run jobs execute pipeline": "gcloud",
        "bq query --use_legacy_sql=false SELECT 1": "bq",
        "gsutil cp source target": "gsutil",
    }
    for text, token in malicious.items():
        errors = module.validate_no_cloud_command_text(text)
        assert errors
        assert any(token in error for error in errors)


def test_execution_api_validator_rejects_malicious_source_snippets() -> None:
    module = _load_module()
    snippets = {
        "import subprocess\n": ["import subprocess"],
        "from subprocess import run\nrun('echo hi', shell=True)\n": ["from subprocess", "run() from subprocess"],
        "import subprocess\nsubprocess.run(['echo', 'hi'])\n": ["subprocess.run"],
        "import subprocess as sp\nsp.Popen(['echo', 'hi'])\n": ["Popen"],
        "import os\nos.system('echo hi')\n": ["os.system"],
        "import os\nos.popen('echo hi')\n": ["os.popen"],
    }
    for snippet, tokens in snippets.items():
        errors = module.validate_no_execution_apis(snippet)
        assert errors
        assert any(any(token in error for token in tokens) for error in errors)


def test_check_mode_passes_and_reports_validation_json(capsys) -> None:
    module = _load_module()
    assert module.main(["--check"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "PASS"
    assert any(check["name"] == "source_execution_apis" for check in result["checks"])


def test_controlled_execution_overrides_are_execution_scoped() -> None:
    module = _load_module()
    overrides = module.build_controlled_execution_overrides(
        run_id="controlled-refresh-20260524T153000Z",
        run_date="2026-05-24",
    )
    assert "--mode" in overrides["args"]
    assert "execute" in overrides["args"]
    assert "--allow-network" in overrides["args"]
    assert overrides["env"]["CLOUD_WRITE_APPROVED"] == "true"
    assert overrides["env"]["BIGQUERY_WRITE_APPROVED"] == "true"
    assert overrides["env"]["BIGQUERY_WAREHOUSE_WRITE_APPROVED"] == "true"
    assert overrides["env"]["BIGQUERY_OPS_WRITE_APPROVED"] == "true"
    assert overrides["env"]["RECOVERY_TABLE_RETENTION_DAYS"] == "45"


def test_monthly_workflow_source_includes_dynamic_execute_overrides_only_when_enabled() -> None:
    module = _load_module()
    plan_source = module.build_monthly_workflow_source(execute_mode=False)
    execute_source = module.build_monthly_workflow_source(execute_mode=True)

    assert "runtime_mode: \"plan_only_readiness\"" in plan_source
    assert "submitted_plan_only_cloud_run_job" in plan_source
    assert "containerOverrides" not in plan_source

    assert "runtime_mode: \"execute_monthly\"" in execute_source
    assert "containerOverrides" in execute_source
    assert "--mode" in execute_source
    assert "execute" in execute_source
    assert "CLOUD_WRITE_APPROVED" in execute_source
    assert "BIGQUERY_WAREHOUSE_WRITE_APPROVED" in execute_source
    assert "RECOVERY_TABLE_RETENTION_DAYS" in execute_source


def test_monthly_workflow_run_date_uses_time_format_not_string_now() -> None:
    module = _load_module()
    execute_source = module.build_monthly_workflow_source(execute_mode=True)
    assert "${text.substring(time.format(sys.now()), 0, 10)}" in execute_source
    assert "${text.substring(string(sys.now()), 0, 10)}" not in execute_source
