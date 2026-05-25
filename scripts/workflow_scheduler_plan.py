from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from typing import Any

DEFAULT_PROJECT_ID = "western-pivot-452008-a6"
DEFAULT_REGION = "asia-southeast1"
DEFAULT_WORKFLOW_NAME = "economic-data-pipeline"
DEFAULT_SCHEDULER_NAME = "economic-data-pipeline-monthly"
DEFAULT_SERVICE_ACCOUNT = "gov-ai-runner@western-pivot-452008-a6.iam.gserviceaccount.com"
DEFAULT_RUN_ID = "{run_id}"
DEFAULT_RUN_DATE = "{run_date}"
DEFAULT_CLOUD_RUN_JOB = "gov-ai-snapshot-plan"

STEP_ORDER = [
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

COMMAND_PATTERNS = (
    ("gcloud", re.compile(r"(?i)\bgcloud\s+")),
    ("bq", re.compile(r"(?i)\bbq\b")),
    ("gsutil", re.compile(r"(?i)\bgsutil\b")),
)

EXECUTION_APIS = {
    "subprocess": {"run", "Popen", "call", "check_call", "check_output"},
    "os": {"system", "popen"},
}


def build_controlled_execution_overrides(*, run_id: str, run_date: str) -> dict[str, Any]:
    return {
        "args": [
            "-m",
            "jobs.scheduled_pipeline",
            "--mode",
            "execute",
            "--run-id",
            run_id,
            "--run-date",
            run_date,
            "--source",
            "all",
            "--allow-network",
            "--runtime-dir",
            "/tmp/gov-ai/runtime",
            "--output-dir",
            "/tmp/gov-ai/output",
        ],
        "env": {
            "CLOUD_WRITE_APPROVED": "true",
            "BIGQUERY_WRITE_APPROVED": "true",
            "BIGQUERY_WAREHOUSE_WRITE_APPROVED": "true",
            "BIGQUERY_OPS_WRITE_APPROVED": "true",
            "RECOVERY_TABLE_RETENTION_DAYS": "45",
        },
    }


def build_monthly_workflow_source(*, execute_mode: bool) -> str:
    if not execute_mode:
        return (
            "main:\n"
            "  params: [args]\n"
            "  steps:\n"
            "    - init:\n"
            "        assign:\n"
            "          - project_id: ${sys.get_env(\"GOOGLE_CLOUD_PROJECT_ID\")}\n"
            "          - location: \"asia-southeast1\"\n"
            "          - job_name: \"gov-ai-snapshot-plan\"\n"
            "          - runtime_mode: \"plan_only_readiness\"\n"
            "    - run_plan_only_job:\n"
            "        call: googleapis.run.v2.projects.locations.jobs.run\n"
            "        args:\n"
            "          name: ${\"projects/\" + project_id + \"/locations/\" + location + \"/jobs/\" + job_name}\n"
            "        result: run_result\n"
            "    - finish:\n"
            "        return:\n"
            "          status: \"submitted_plan_only_cloud_run_job\"\n"
            "          runtime_mode: ${runtime_mode}\n"
            "          run_result: ${run_result}\n"
        )

    overrides = build_controlled_execution_overrides(
        run_id="${\"scheduled-refresh-\" + string(int(sys.now()))}",
        run_date="${text.substring(time.format(sys.now()), 0, 10)}",
    )
    args_yaml = ", ".join([f"\"{item}\"" for item in overrides["args"]])
    env_yaml = "\n".join(
        [
            f"                      - name: {key}\n"
            f"                        value: \"{value}\""
            for key, value in overrides["env"].items()
        ]
    )
    return (
        "main:\n"
        "  params: [args]\n"
        "  steps:\n"
        "    - init:\n"
        "        assign:\n"
        "          - project_id: ${sys.get_env(\"GOOGLE_CLOUD_PROJECT_ID\")}\n"
        "          - location: \"asia-southeast1\"\n"
        f"          - job_name: \"{DEFAULT_CLOUD_RUN_JOB}\"\n"
        "          - runtime_mode: \"execute_monthly\"\n"
        "    - run_execute_job:\n"
        "        call: googleapis.run.v2.projects.locations.jobs.run\n"
        "        args:\n"
        "          name: ${\"projects/\" + project_id + \"/locations/\" + location + \"/jobs/\" + job_name}\n"
        "          body:\n"
        "            overrides:\n"
        "              containerOverrides:\n"
        "                - args:\n"
        f"                    [{args_yaml}]\n"
        "                  env:\n"
        f"{env_yaml}\n"
        "        result: run_result\n"
        "    - finish:\n"
        "        return:\n"
        "          status: \"submitted_execute_cloud_run_job\"\n"
        "          runtime_mode: ${runtime_mode}\n"
        "          run_result: ${run_result}\n"
    )


def validate_no_cloud_command_text(text: str) -> list[str]:
    errors: list[str] = []
    for label, pattern in COMMAND_PATTERNS:
        if pattern.search(text or ""):
            errors.append(f"forbidden cloud command text found: {label}")
    return errors


def validate_no_execution_apis(source_text: str) -> list[str]:
    try:
        tree = ast.parse(source_text)
    except SyntaxError as exc:
        return [f"source parse failed: {exc.msg}"]

    errors: list[str] = []
    module_aliases: dict[str, str] = {}
    imported_names: dict[str, str] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound_name = alias.asname or alias.name
                module_aliases[bound_name] = alias.name
                if alias.name == "subprocess":
                    errors.append("forbidden execution API: import subprocess")
                if alias.name == "os":
                    module_aliases[bound_name] = "os"
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                bound_name = alias.asname or alias.name
                imported_names[bound_name] = module
            if module == "subprocess":
                errors.append("forbidden execution API: from subprocess import ...")
            if module == "os" and any((alias.asname or alias.name) in EXECUTION_APIS["os"] or alias.name in EXECUTION_APIS["os"] for alias in node.names):
                errors.append("forbidden execution API: from os import ...")

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            base_name = func.value.id
            base_module = module_aliases.get(base_name, imported_names.get(base_name))
            if base_module == "subprocess" and func.attr in EXECUTION_APIS["subprocess"]:
                errors.append(f"forbidden execution API: {base_name}.{func.attr}()")
            if base_module == "os" and func.attr in EXECUTION_APIS["os"]:
                errors.append(f"forbidden execution API: {base_name}.{func.attr}()")
        elif isinstance(func, ast.Name):
            base_module = imported_names.get(func.id)
            if base_module == "subprocess":
                errors.append(f"forbidden execution API: {func.id}() from subprocess")
            if base_module == "os":
                errors.append(f"forbidden execution API: {func.id}() from os")

    return errors


def build_workflow_steps() -> list[dict[str, Any]]:
    return [
        {
            "step": "initialize_run",
            "description": "Initialize the scheduled run context and offline metadata for the planning template.",
            "required": True,
            "offline_only": True,
        },
        {
            "step": "fetch_official_sources_and_decide_change",
            "description": "Acquire official sources and compare the candidate manifest against the last successful snapshot.",
            "required": True,
        },
        {
            "step": "branch_unchanged_skip_or_changed_continue",
            "description": "Unchanged branch stops without publish; changed branch continues into candidate validation.",
            "required": True,
            "branch": {
                "unchanged": {
                    "status": "SKIPPED_UNCHANGED",
                    "publish": False,
                    "warehouse_publish_performed": False,
                    "last_successful_updated": False,
                },
                "changed": {
                    "status": "DRY_RUN_CHANGED",
                    "continue": True,
                    "candidate_validation_required": True,
                    "publish_only_after_validation": True,
                    "record_success_freshness_after_publish": True,
                },
            },
        },
        {
            "step": "persist_bronze_and_manifests_if_changed",
            "description": "Persist bronze snapshots and manifests only when the source fingerprint changed.",
            "required": True,
            "branch_condition": "changed",
        },
        {
            "step": "build_and_validate_silver_candidate",
            "description": "Build the Silver candidate and validate its contract before any publish path continues.",
            "required": True,
            "branch_condition": "changed",
        },
        {
            "step": "build_and_validate_gold_analytics_candidates",
            "description": "Build Gold and Analytics candidates and validate them before production publish.",
            "required": True,
            "branch_condition": "changed",
        },
        {
            "step": "run_data_quality_gate",
            "description": "Run the data-quality gate before production publish is allowed.",
            "required": True,
            "branch_condition": "changed",
        },
        {
            "step": "publish_bigquery_production_if_valid",
            "description": "Publish to BigQuery production only after validation and data-quality PASS.",
            "required": True,
            "branch_condition": "changed",
        },
        {
            "step": "record_success_freshness",
            "description": "Record freshness metadata only after a successful production publish.",
            "required": True,
            "branch_condition": "changed",
        },
        {
            "step": "backend_freshness_smoke",
            "description": "Offline planning placeholder for a later backend freshness smoke; no backend endpoint is added here.",
            "required": True,
            "offline_only": True,
        },
    ]


def build_workflow_template(steps: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "template_kind": "workflow",
        "execution_scope": "offline_template_only",
        "main_path": "bigquery_direct",
        "workflow_name": DEFAULT_WORKFLOW_NAME,
        "project_id": DEFAULT_PROJECT_ID,
        "region": DEFAULT_REGION,
        "service_account": DEFAULT_SERVICE_ACCOUNT,
        "cloud_run_job_placeholder": {
            "name": "gov-ai-scheduled-pipeline",
            "mode": "offline_placeholder",
            "purpose": "future runtime binding only",
        },
        "steps": steps,
        "branch_semantics": {
            "unchanged": {
                "terminal_status": "SKIPPED_UNCHANGED",
                "warehouse_publish_performed": False,
                "last_successful_updated": False,
                "publish": False,
            },
            "changed": {
                "publish_only_after_validation": True,
                "record_success_freshness_after_publish": True,
            },
        },
        "notes": [
            "No PostgreSQL dependency is required in the scheduled main path.",
            "No cloud side effects are authorized by this template.",
        ],
    }


def build_scheduler_template() -> dict[str, Any]:
    return {
        "template_kind": "scheduler",
        "name": DEFAULT_SCHEDULER_NAME,
        "schedule": "0 2 5 * *",
        "time_zone": "UTC",
        "paused": True,
        "state": "PAUSED",
        "activation_requires_later_approval": True,
        "workflow_name": DEFAULT_WORKFLOW_NAME,
        "project_id": DEFAULT_PROJECT_ID,
        "region": DEFAULT_REGION,
        "service_account": DEFAULT_SERVICE_ACCOUNT,
        "note": "Keep paused until later user approval after readiness review.",
    }


def render_yaml(value: Any, indent: int = 0) -> str:
    space = " " * indent

    def render_scalar(item: Any) -> str:
        if item is True:
            return "true"
        if item is False:
            return "false"
        if item is None:
            return "null"
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            return str(item)
        if isinstance(item, str):
            if "\n" in item:
                return item
            return json.dumps(item, ensure_ascii=False)
        return json.dumps(item, ensure_ascii=False)

    if isinstance(value, dict):
        if not value:
            return f"{space}{{}}"
        lines: list[str] = []
        for key, item in value.items():
            rendered_key = key if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", str(key)) else json.dumps(
                str(key), ensure_ascii=False
            )
            if isinstance(item, dict):
                if item:
                    lines.append(f"{space}{rendered_key}:")
                    lines.append(render_yaml(item, indent + 2))
                else:
                    lines.append(f"{space}{rendered_key}: {{}}")
            elif isinstance(item, list):
                if item:
                    lines.append(f"{space}{rendered_key}:")
                    lines.append(render_yaml(item, indent + 2))
                else:
                    lines.append(f"{space}{rendered_key}: []")
            elif isinstance(item, str) and "\n" in item:
                lines.append(f"{space}{rendered_key}: |")
                for line in item.splitlines():
                    lines.append(f"{space}  {line}")
            else:
                lines.append(f"{space}{rendered_key}: {render_scalar(item)}")
        return "\n".join(lines)

    if isinstance(value, list):
        if not value:
            return f"{space}[]"
        lines = []
        for item in value:
            if isinstance(item, dict):
                if item:
                    lines.append(f"{space}-")
                    lines.append(render_yaml(item, indent + 2))
                else:
                    lines.append(f"{space}- {{}}")
            elif isinstance(item, list):
                if item:
                    lines.append(f"{space}-")
                    lines.append(render_yaml(item, indent + 2))
                else:
                    lines.append(f"{space}- []")
            elif isinstance(item, str) and "\n" in item:
                lines.append(f"{space}- |")
                for line in item.splitlines():
                    lines.append(f"{space}  {line}")
            else:
                lines.append(f"{space}- {render_scalar(item)}")
        return "\n".join(lines)

    if isinstance(value, str) and "\n" in value:
        lines = [f"{space}|"]
        for line in value.splitlines():
            lines.append(f"{space}  {line}")
        return "\n".join(lines)

    return f"{space}{render_scalar(value)}"


def _plan_without_validation(plan: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in plan.items() if key != "validation"}


def render_plan_json(plan: dict[str, Any]) -> str:
    return json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True)


def render_plan_yaml(plan: dict[str, Any]) -> str:
    return render_yaml(plan)


def build_plan() -> dict[str, Any]:
    steps = build_workflow_steps()
    workflow_template = build_workflow_template(steps)
    scheduler_template = build_scheduler_template()
    return {
        "generated_by": "workflow_scheduler_plan",
        "workflow": {
            "name": DEFAULT_WORKFLOW_NAME,
            "project_id": DEFAULT_PROJECT_ID,
            "region": DEFAULT_REGION,
            "service_account": DEFAULT_SERVICE_ACCOUNT,
            "main_path": "bigquery_direct",
            "orchestration_order": steps,
            "cloud_run_job_placeholder": {
                "name": "gov-ai-scheduled-pipeline",
                "mode": "offline_placeholder",
                "purpose": "future runtime binding only",
            },
            "branch_semantics": {
                "unchanged": {
                    "terminal_status": "SKIPPED_UNCHANGED",
                    "warehouse_publish_performed": False,
                    "last_successful_updated": False,
                    "publish": False,
                },
                "changed": {
                    "publish_only_after_validation": True,
                    "record_success_freshness_after_publish": True,
                },
            },
            "notes": [
                "No PostgreSQL dependency is required in the scheduled main path.",
                "No cloud side effects are authorized by this template.",
            ],
            "yaml_template": render_yaml(workflow_template),
        },
        "scheduler": {
            "name": DEFAULT_SCHEDULER_NAME,
            "schedule": "0 2 5 * *",
            "time_zone": "UTC",
            "paused": True,
            "state": "PAUSED",
            "activation_requires_later_approval": True,
            "project_id": DEFAULT_PROJECT_ID,
            "region": DEFAULT_REGION,
            "workflow_name": DEFAULT_WORKFLOW_NAME,
            "service_account": DEFAULT_SERVICE_ACCOUNT,
            "note": "Keep paused until later user approval after readiness review.",
            "yaml_template": render_yaml(scheduler_template),
        },
        "required_path_constraints": {
            "main_path": "bigquery_direct",
            "postgres_required_in_main_path": False,
            "analytics_worker_postgres_required": False,
        },
        "side_effect_guardrails": [
            "Template and plan only: no deployment and no cloud command execution.",
            "Scheduler template remains PAUSED.",
            "Unchanged branch must produce SKIPPED_UNCHANGED with no publish and no freshness update.",
        ],
    }


def validate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    errors: list[str] = []

    expected_order = STEP_ORDER
    workflow = plan.get("workflow", {})
    scheduler = plan.get("scheduler", {})

    actual_order = [item.get("step") for item in workflow.get("orchestration_order", [])]
    workflow_order_ok = actual_order == expected_order
    if not workflow_order_ok:
        errors.append("workflow orchestration order mismatch")
    checks.append({"name": "workflow_order", "status": "PASS" if workflow_order_ok else "FAIL"})

    template_workflow_yaml = str(workflow.get("yaml_template", "") or "")
    template_scheduler_yaml = str(scheduler.get("yaml_template", "") or "")
    templates_present = bool(template_workflow_yaml.strip()) and bool(template_scheduler_yaml.strip())
    if not templates_present:
        errors.append("workflow/scheduler template output is missing")
    checks.append({"name": "template_outputs_present", "status": "PASS" if templates_present else "FAIL"})

    workflow_semantic_tokens = [
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
        "SKIPPED_UNCHANGED",
        "warehouse_publish_performed: false",
        "last_successful_updated: false",
        "bigquery_direct",
    ]
    workflow_template_ok = templates_present and all(token in template_workflow_yaml for token in workflow_semantic_tokens)
    if not workflow_template_ok:
        errors.append("workflow template does not contain required BigQuery-direct semantics")
    checks.append({"name": "workflow_template_semantics", "status": "PASS" if workflow_template_ok else "FAIL"})

    scheduler_semantic_tokens = [
        "0 2 5 * *",
        "UTC",
        "PAUSED",
        "paused: true",
        "activation_requires_later_approval: true",
        "economic-data-pipeline-monthly",
    ]
    scheduler_template_ok = templates_present and all(token in template_scheduler_yaml for token in scheduler_semantic_tokens)
    if not scheduler_template_ok:
        errors.append("scheduler template does not contain required monthly paused semantics")
    checks.append({"name": "scheduler_template_semantics", "status": "PASS" if scheduler_template_ok else "FAIL"})

    scheduler_ok = (
        scheduler.get("schedule") == "0 2 5 * *"
        and scheduler.get("time_zone") == "UTC"
        and scheduler.get("paused") is True
        and scheduler.get("state") == "PAUSED"
        and scheduler.get("activation_requires_later_approval") is True
    )
    if not scheduler_ok:
        errors.append("scheduler must remain monthly UTC and paused")
    checks.append({"name": "scheduler_monthly_paused", "status": "PASS" if scheduler_ok else "FAIL"})

    constraints = plan.get("required_path_constraints", {})
    no_pg = (
        constraints.get("main_path") == "bigquery_direct"
        and constraints.get("postgres_required_in_main_path") is False
        and constraints.get("analytics_worker_postgres_required") is False
    )
    if not no_pg:
        errors.append("postgres dependency still present in scheduled main path")
    checks.append({"name": "no_postgres_main_path_dependency", "status": "PASS" if no_pg else "FAIL"})

    structured_branch = workflow.get("branch_semantics", {}).get("unchanged", {})
    structured_branch_ok = (
        structured_branch.get("terminal_status") == "SKIPPED_UNCHANGED"
        and structured_branch.get("warehouse_publish_performed") is False
        and structured_branch.get("last_successful_updated") is False
        and structured_branch.get("publish") is False
    )
    if not structured_branch_ok:
        errors.append("structured unchanged branch semantics are not preserved")
    checks.append({"name": "structured_unchanged_branch_semantics", "status": "PASS" if structured_branch_ok else "FAIL"})

    branch = workflow.get("orchestration_order", [])[2].get("branch", {}) if len(workflow.get("orchestration_order", [])) > 2 else {}
    unchanged = branch.get("unchanged", {})
    unchanged_ok = (
        unchanged.get("status") == "SKIPPED_UNCHANGED"
        and unchanged.get("publish") is False
        and unchanged.get("warehouse_publish_performed") is False
        and unchanged.get("last_successful_updated") is False
    )
    if not unchanged_ok:
        errors.append("unchanged branch must preserve skip/no-publish/no-freshness-update semantics")
    checks.append({"name": "unchanged_branch_semantics", "status": "PASS" if unchanged_ok else "FAIL"})

    plan_snapshot = _plan_without_validation(plan)
    rendered_json = render_plan_json(plan_snapshot)
    rendered_yaml = render_plan_yaml(plan_snapshot)

    cloud_command_checks = (
        ("workflow_yaml_template", template_workflow_yaml),
        ("scheduler_yaml_template", template_scheduler_yaml),
        ("rendered_json", rendered_json),
        ("rendered_yaml", rendered_yaml),
    )
    cloud_text_ok = True
    for label, text in cloud_command_checks:
        label_errors = validate_no_cloud_command_text(text)
        if label_errors:
            cloud_text_ok = False
            errors.extend(f"{label}: {error}" for error in label_errors)
    checks.append({"name": "no_cloud_command_text", "status": "PASS" if cloud_text_ok else "FAIL"})

    return {"status": "PASS" if not errors else "FAIL", "errors": errors, "checks": checks}


def validate_source_execution_apis(source_text: str) -> dict[str, Any]:
    errors = validate_no_execution_apis(source_text)
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "checks": [
            {
                "name": "source_execution_apis",
                "status": "PASS" if not errors else "FAIL",
            }
        ],
    }


def build_check_result(plan: dict[str, Any], source_text: str) -> dict[str, Any]:
    plan_validation = validate_plan(plan)
    source_validation = validate_source_execution_apis(source_text)
    errors = [*plan_validation["errors"], *source_validation["errors"]]
    checks = [*plan_validation["checks"], *source_validation["checks"]]
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "checks": checks,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate offline workflow and scheduler planning templates.")
    parser.add_argument("--format", choices=("text", "json", "yaml"), default="text")
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def render_text(plan: dict[str, Any]) -> str:
    lines = [
        "Workflow and Scheduler Planning (BigQuery-direct)",
        f"Workflow: {plan['workflow']['name']}",
        f"Scheduler: {plan['scheduler']['name']}",
        f"Schedule: {plan['scheduler']['schedule']} UTC",
        f"Paused: {plan['scheduler']['paused']}",
        "",
        "Ordered steps:",
    ]
    for item in plan["workflow"]["orchestration_order"]:
        lines.append(f"- {item['step']}")
    lines.extend(
        [
            "",
            "Unchanged path:",
            "- status=SKIPPED_UNCHANGED",
            "- publish=false",
            "- warehouse_publish_performed=false",
            "- last_successful_updated=false",
            "",
            "Changed path:",
            "- build candidates -> validate -> data quality -> publish -> record success freshness",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    plan = build_plan()
    source_text = Path(__file__).read_text(encoding="utf-8")

    if args.check:
        validation = build_check_result(plan, source_text)
        print(json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if validation["status"] == "PASS" else 1

    plan["validation"] = validate_plan(plan)
    if args.format == "json":
        print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
    elif args.format == "yaml":
        print(render_yaml(plan))
    else:
        print(render_text(plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
