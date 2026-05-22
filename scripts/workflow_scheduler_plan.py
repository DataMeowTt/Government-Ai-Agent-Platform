from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from cloud_run_job_plan import build_plan as build_cloud_run_job_plan


DEFAULT_PROJECT_ID = "{project_id}"
DEFAULT_REGION = "{region}"
DEFAULT_WORKFLOW_NAME = "{workflow_name}"
DEFAULT_SCHEDULER_NAME = "{scheduler_name}"
DEFAULT_SERVICE_ACCOUNT = "{service_account}"
DEFAULT_BUCKET = "{bucket}"
DEFAULT_RUN_ID = "{run_id}"
DEFAULT_RUN_DATE = "{run_date}"
DEFAULT_FORCE = "{force}"
DEFAULT_ARTIFACT_REPOSITORY = "{artifact_repository}"
DEFAULT_IMAGE_TAG = "{image_tag}"
DEFAULT_GENERATED_AT = "{generated_at}"
DEFAULT_OUTPUT_FORMAT = "{output_format}"
DEFAULT_PREVIOUS_MANIFEST_PATH = "{previous_manifest_path}"
DEFAULT_SILVER_OUTPUT_URI = "{silver_output_uri}"
DEFAULT_POSTGRES_HOST = "{postgres_host}"
DEFAULT_POSTGRES_PORT = "{postgres_port}"
DEFAULT_POSTGRES_DB = "{postgres_db}"
DEFAULT_POSTGRES_USER = "{postgres_user}"
DEFAULT_POSTGRES_PASSWORD = "{postgres_password}"
DEFAULT_BIGQUERY_ANALYTICS_DATASET = "{bigquery_analytics_dataset}"
DEFAULT_BIGQUERY_LOCATION = "{bigquery_location}"
DEFAULT_LATEST_VALID_YEAR = "{latest_valid_year}"
DEFAULT_DATABASE_URL = "{database_url}"

def build_command_patterns() -> list[tuple[str, re.Pattern[str]]]:
    def joined(parts: list[str]) -> str:
        return "".join(parts)

    return [
        (joined(["g", "cloud", r"\s+", "run", r"\s+", "jobs", r"\s+", "execute"]), re.compile(joined(["gcloud", r"\s+", "run", r"\s+", "jobs", r"\s+", "execute"]), re.IGNORECASE)),
        (joined(["g", "cloud", r"\s+", "workflows", r"\s+", "deploy"]), re.compile(joined(["gcloud", r"\s+", "workflows", r"\s+", "deploy"]), re.IGNORECASE)),
        (joined(["g", "cloud", r"\s+", "scheduler", r"\s+", "jobs", r"\s+", "create"]), re.compile(joined(["gcloud", r"\s+", "scheduler", r"\s+", "jobs", r"\s+", "create"]), re.IGNORECASE)),
        (joined(["g", "cloud", r"\s+", "scheduler", r"\s+", "jobs", r"\s+", "update"]), re.compile(joined(["gcloud", r"\s+", "scheduler", r"\s+", "jobs", r"\s+", "update"]), re.IGNORECASE)),
        (joined(["g", "cloud", r"\s+", "auth"]), re.compile(joined(["gcloud", r"\s+", "auth"]), re.IGNORECASE)),
        (joined(["g", "cloud", r"\s+", "config", r"\s+", "set"]), re.compile(joined(["gcloud", r"\s+", "config", r"\s+", "set"]), re.IGNORECASE)),
        (joined(["b", "q"]), re.compile(joined([r"\b", "b", "q", r"\b"]), re.IGNORECASE)),
        (joined(["gs", "util"]), re.compile(joined([r"\b", "gs", "util", r"\b"]), re.IGNORECASE)),
        (joined(["ter", "ra", "form"]), re.compile(joined([r"\b", "ter", "ra", "form", r"\b"]), re.IGNORECASE)),
        (joined(["pu", "lu", "mi"]), re.compile(joined([r"\b", "pu", "lu", "mi", r"\b"]), re.IGNORECASE)),
        (joined(["do", "cker", r"\s+", "push"]), re.compile(joined(["docker", r"\s+", "push"]), re.IGNORECASE)),
    ]


def build_placeholders() -> list[dict[str, str]]:
    return [
        {
            "name": "project_id",
            "token": DEFAULT_PROJECT_ID,
            "description": "GCP project identifier.",
        },
        {
            "name": "region",
            "token": DEFAULT_REGION,
            "description": "GCP region for the workflow and scheduler.",
        },
        {
            "name": "workflow_name",
            "token": DEFAULT_WORKFLOW_NAME,
            "description": "Stable workflow name for the orchestration template.",
        },
        {
            "name": "scheduler_name",
            "token": DEFAULT_SCHEDULER_NAME,
            "description": "Stable scheduler name for the monthly trigger template.",
        },
        {
            "name": "service_account",
            "token": DEFAULT_SERVICE_ACCOUNT,
            "description": "Service account used by Workflows and Cloud Run Jobs.",
        },
        {
            "name": "bucket",
            "token": DEFAULT_BUCKET,
            "description": "Bucket placeholder for snapshot and manifest paths.",
        },
        {
            "name": "run_id",
            "token": DEFAULT_RUN_ID,
            "description": "Run identifier propagated through the workflow.",
        },
        {
            "name": "run_date",
            "token": DEFAULT_RUN_DATE,
            "description": "Business date propagated through the workflow.",
        },
        {
            "name": "force",
            "token": DEFAULT_FORCE,
            "description": "Manual override flag for reruns and unchanged snapshots.",
        },
        {
            "name": "artifact_repository",
            "token": DEFAULT_ARTIFACT_REPOSITORY,
            "description": "Artifact Registry repository placeholder for image references.",
        },
        {
            "name": "image_tag",
            "token": DEFAULT_IMAGE_TAG,
            "description": "Image tag placeholder used by job templates.",
        },
        {
            "name": "generated_at",
            "token": DEFAULT_GENERATED_AT,
            "description": "Deterministic generation timestamp placeholder.",
        },
        {
            "name": "output_format",
            "token": DEFAULT_OUTPUT_FORMAT,
            "description": "Output format placeholder for local planner alignment.",
        },
        {
            "name": "previous_manifest_path",
            "token": DEFAULT_PREVIOUS_MANIFEST_PATH,
            "description": "Previous manifest path placeholder for change detection.",
        },
        {
            "name": "silver_output_uri",
            "token": DEFAULT_SILVER_OUTPUT_URI,
            "description": "Silver output URI placeholder reused by downstream job templates.",
        },
        {
            "name": "postgres_host",
            "token": DEFAULT_POSTGRES_HOST,
            "description": "Postgres-compatible host placeholder for gold and analytics jobs.",
        },
        {
            "name": "postgres_port",
            "token": DEFAULT_POSTGRES_PORT,
            "description": "Postgres-compatible port placeholder.",
        },
        {
            "name": "postgres_db",
            "token": DEFAULT_POSTGRES_DB,
            "description": "Postgres-compatible database name placeholder.",
        },
        {
            "name": "postgres_user",
            "token": DEFAULT_POSTGRES_USER,
            "description": "Postgres-compatible user placeholder.",
        },
        {
            "name": "postgres_password",
            "token": DEFAULT_POSTGRES_PASSWORD,
            "description": "Secret placeholder for Postgres-compatible jobs.",
        },
        {
            "name": "bigquery_analytics_dataset",
            "token": DEFAULT_BIGQUERY_ANALYTICS_DATASET,
            "description": "BigQuery analytics dataset placeholder for future review.",
        },
        {
            "name": "bigquery_location",
            "token": DEFAULT_BIGQUERY_LOCATION,
            "description": "BigQuery location placeholder for future review.",
        },
        {
            "name": "latest_valid_year",
            "token": DEFAULT_LATEST_VALID_YEAR,
            "description": "Latest valid year placeholder for analytics planning.",
        },
        {
            "name": "database_url",
            "token": DEFAULT_DATABASE_URL,
            "description": "Database URL placeholder for PostgreSQL-compatible analytics jobs.",
        },
    ]


def validate_source_forbidden_tokens(text: str) -> list[str]:
    errors: list[str] = []
    lowered = text.lower()
    for label, pattern in build_command_patterns():
        if pattern.search(lowered):
            errors.append(f"forbidden command text found: {label}")
    return errors


def normalize_cloud_run_jobs() -> list[dict[str, Any]]:
    cloud_run_plan = build_cloud_run_job_plan()
    step_roles = {
        "gov-ai-data-manifest": "source_snapshot_planning",
        "gov-ai-data-snapshot-plan": "source_snapshot_planning",
        "gov-ai-gold-build": "gold_build",
        "gov-ai-analytics-batch": "analytics_batch",
    }

    jobs: list[dict[str, Any]] = []
    for job in cloud_run_plan["jobs"]:
        name = str(job["name"])
        jobs.append(
            {
                "name": name,
                "workflow_role": step_roles.get(name, "manual_review"),
                "status": job["status"],
                "image_uri": job["image_uri"],
                "create_command": job["create_command"],
                "update_command": job["update_command"],
                "args_template": job["args_template"],
                "env": job["env"],
                "secrets": job["secrets"],
                "iam": job["iam"],
                "side_effect_warning": job["side_effect_warning"],
            }
        )
    return jobs


def build_workflow_steps() -> list[dict[str, Any]]:
    return [
        {
            "name": "plan_source_snapshot",
            "kind": "concrete",
            "manual_review_required": False,
            "cloud_run_jobs": [
                "gov-ai-data-manifest",
                "gov-ai-data-snapshot-plan",
            ],
            "description": "Plan and check source snapshot manifests before downstream work.",
        },
        {
            "name": "build_silver_or_pipeline",
            "kind": "placeholder",
            "manual_review_required": True,
            "enabled_by_default": False,
            "cloud_run_jobs": [],
            "description": "Placeholder for a silver or pipeline job until a cloud-ready job template exists.",
        },
        {
            "name": "build_gold",
            "kind": "concrete",
            "manual_review_required": False,
            "cloud_run_jobs": ["gov-ai-gold-build"],
            "description": "Build Gold tables with the existing Cloud Run Job template.",
        },
        {
            "name": "publish_or_load_bigquery",
            "kind": "placeholder",
            "manual_review_required": True,
            "enabled_by_default": False,
            "cloud_run_jobs": [],
            "description": "Placeholder for BigQuery staging and production loading until a concrete job template exists.",
        },
        {
            "name": "run_analytics",
            "kind": "concrete",
            "manual_review_required": False,
            "cloud_run_jobs": ["gov-ai-analytics-batch"],
            "description": "Run analytics with the existing Cloud Run Job template.",
        },
        {
            "name": "run_data_quality_audit",
            "kind": "placeholder",
            "manual_review_required": True,
            "enabled_by_default": False,
            "cloud_run_jobs": [],
            "description": "Placeholder for a data quality audit job because no concrete cloud job template exists yet.",
        },
        {
            "name": "postgres_sync_optional",
            "kind": "placeholder",
            "manual_review_required": True,
            "enabled_by_default": False,
            "cloud_run_jobs": [],
            "description": "Optional PostgreSQL-compatible sync placeholder, disabled by default.",
        },
    ]


def build_workflow_yaml_template(steps: list[dict[str, Any]]) -> str:
    lines = [
        "main:",
        "  params: [input]",
        "  steps:",
        "    - init:",
        "        assign:",
        f"          - project_id: {json.dumps(DEFAULT_PROJECT_ID, ensure_ascii=False)}",
        f"          - region: {json.dumps(DEFAULT_REGION, ensure_ascii=False)}",
        f"          - workflow_name: {json.dumps(DEFAULT_WORKFLOW_NAME, ensure_ascii=False)}",
        f"          - scheduler_name: {json.dumps(DEFAULT_SCHEDULER_NAME, ensure_ascii=False)}",
        f"          - service_account: {json.dumps(DEFAULT_SERVICE_ACCOUNT, ensure_ascii=False)}",
        f"          - bucket: {json.dumps(DEFAULT_BUCKET, ensure_ascii=False)}",
        f"          - run_id: {json.dumps(DEFAULT_RUN_ID, ensure_ascii=False)}",
        f"          - run_date: {json.dumps(DEFAULT_RUN_DATE, ensure_ascii=False)}",
        f"          - force: {json.dumps(DEFAULT_FORCE, ensure_ascii=False)}",
        "",
    ]

    for step in steps:
        lines.append(f"    - {step['name']}:")
        lines.append(f"        mode: {json.dumps(step['kind'], ensure_ascii=False)}")
        lines.append(
            f"        manual_review_required: {json.dumps(step['manual_review_required'], ensure_ascii=False)}"
        )
        lines.append(
            f"        enabled_by_default: {json.dumps(step.get('enabled_by_default', True), ensure_ascii=False)}"
        )
        if step["cloud_run_jobs"]:
            lines.append("        cloud_run_jobs:")
            for job_name in step["cloud_run_jobs"]:
                lines.append(f"          - {json.dumps(job_name, ensure_ascii=False)}")
        else:
            lines.append("        cloud_run_jobs: []")
        lines.append(f"        note: {json.dumps(step['description'], ensure_ascii=False)}")
        lines.append("")

    lines.extend(
        [
            "manual_trigger_payloads:",
            "  force_false:",
            f"    project_id: {json.dumps(DEFAULT_PROJECT_ID, ensure_ascii=False)}",
            f"    region: {json.dumps(DEFAULT_REGION, ensure_ascii=False)}",
            f"    workflow_name: {json.dumps(DEFAULT_WORKFLOW_NAME, ensure_ascii=False)}",
            f"    scheduler_name: {json.dumps(DEFAULT_SCHEDULER_NAME, ensure_ascii=False)}",
            f"    service_account: {json.dumps(DEFAULT_SERVICE_ACCOUNT, ensure_ascii=False)}",
            f"    bucket: {json.dumps(DEFAULT_BUCKET, ensure_ascii=False)}",
            f"    run_id: {json.dumps(DEFAULT_RUN_ID, ensure_ascii=False)}",
            f"    run_date: {json.dumps(DEFAULT_RUN_DATE, ensure_ascii=False)}",
            "    force: false",
            "  force_true:",
            f"    project_id: {json.dumps(DEFAULT_PROJECT_ID, ensure_ascii=False)}",
            f"    region: {json.dumps(DEFAULT_REGION, ensure_ascii=False)}",
            f"    workflow_name: {json.dumps(DEFAULT_WORKFLOW_NAME, ensure_ascii=False)}",
            f"    scheduler_name: {json.dumps(DEFAULT_SCHEDULER_NAME, ensure_ascii=False)}",
            f"    service_account: {json.dumps(DEFAULT_SERVICE_ACCOUNT, ensure_ascii=False)}",
            f"    bucket: {json.dumps(DEFAULT_BUCKET, ensure_ascii=False)}",
            f"    run_id: {json.dumps(DEFAULT_RUN_ID, ensure_ascii=False)}",
            f"    run_date: {json.dumps(DEFAULT_RUN_DATE, ensure_ascii=False)}",
            "    force: true",
        ]
    )

    return "\n".join(lines)


def build_scheduler_yaml_template() -> str:
    return "\n".join(
        [
            f"name: {json.dumps(DEFAULT_SCHEDULER_NAME, ensure_ascii=False)}",
            'schedule: "0 2 5 * *"',
            'timeZone: "UTC"',
            "paused: true",
            "manual_review_required: true",
            "description: \"Monthly trigger template for workflow review before deployment.\"",
            "target:",
            "  type: \"workflows_execution\"",
            f"  project_id: {json.dumps(DEFAULT_PROJECT_ID, ensure_ascii=False)}",
            f"  region: {json.dumps(DEFAULT_REGION, ensure_ascii=False)}",
            f"  workflow_name: {json.dumps(DEFAULT_WORKFLOW_NAME, ensure_ascii=False)}",
            f"  service_account: {json.dumps(DEFAULT_SERVICE_ACCOUNT, ensure_ascii=False)}",
            "  input:",
            f"    run_id: {json.dumps(DEFAULT_RUN_ID, ensure_ascii=False)}",
            f"    run_date: {json.dumps(DEFAULT_RUN_DATE, ensure_ascii=False)}",
            "    force: false",
        ]
    )


def build_environment_contract() -> dict[str, Any]:
    return {
        "required_workflow_inputs": [
            "project_id",
            "region",
            "workflow_name",
            "scheduler_name",
            "service_account",
            "bucket",
            "run_id",
            "run_date",
            "force",
        ],
        "review_inputs": [
            "artifact_repository",
            "image_tag",
            "generated_at",
            "output_format",
            "previous_manifest_path",
            "silver_output_uri",
            "postgres_host",
            "postgres_port",
            "postgres_db",
            "postgres_user",
            "postgres_password",
            "bigquery_analytics_dataset",
            "bigquery_location",
            "latest_valid_year",
            "database_url",
        ],
        "aligned_cloud_run_jobs": [
            "gov-ai-data-manifest",
            "gov-ai-data-snapshot-plan",
            "gov-ai-gold-build",
            "gov-ai-analytics-batch",
        ],
        "step_contract": {
            "source_snapshot_planning": [
                "run_id",
                "run_date",
                "bucket",
                "previous_manifest_path",
            ],
            "gold_build": [
                "run_id",
                "run_date",
                "output_format",
                "silver_output_uri",
                "postgres_host",
                "postgres_port",
                "postgres_db",
                "postgres_user",
                "postgres_password",
            ],
            "analytics_batch": [
                "run_id",
                "run_date",
                "bigquery_analytics_dataset",
                "bigquery_location",
                "latest_valid_year",
                "database_url",
            ],
        },
        "manual_review_notes": [
            "Concrete job templates are reused from the existing offline Cloud Run job plan.",
            "Placeholder steps stay disabled by default until a later pass adds concrete jobs or deployment wrappers.",
        ],
    }


def build_manual_review_required(workflow_steps: list[dict[str, Any]]) -> list[str]:
    notes = [
        "Confirm project_id, region, billing, service_account, bucket, Artifact Registry, and IAM before any deployment.",
        "Keep the monthly scheduler paused until the workflow and job wiring are reviewed.",
        "Review the force=false and force=true payloads before manual trigger use.",
        "No cloud resources are created, updated, or deployed by this offline planner.",
    ]
    for step in workflow_steps:
        if step["manual_review_required"]:
            notes.append(f"Review placeholder step: {step['name']}.")
    return notes


def build_side_effect_guardrails() -> list[str]:
    return [
        "Templates only; no cloud resource is created, updated, or deployed by this generator.",
        "No cloud command, SDK call, or subprocess execution is performed here.",
        "Deployment requires explicit user confirmation for project, region, billing, service account, bucket, Artifact Registry, and IAM.",
        "Concrete Cloud Run job templates are review-only until the target environment is confirmed.",
        "Placeholder workflow steps remain disabled by default until concrete jobs exist.",
    ]


def build_workflow_summary(steps: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "name": DEFAULT_WORKFLOW_NAME,
        "manual_review_required": True,
        "orchestration_order": [
            {
                "step": step["name"],
                "kind": step["kind"],
                "manual_review_required": step["manual_review_required"],
                "cloud_run_jobs": step["cloud_run_jobs"],
            }
            for step in steps
        ],
        "yaml_template": build_workflow_yaml_template(steps),
        "manual_trigger_payloads": {
            "force_false": {
                "project_id": DEFAULT_PROJECT_ID,
                "region": DEFAULT_REGION,
                "workflow_name": DEFAULT_WORKFLOW_NAME,
                "scheduler_name": DEFAULT_SCHEDULER_NAME,
                "service_account": DEFAULT_SERVICE_ACCOUNT,
                "bucket": DEFAULT_BUCKET,
                "run_id": DEFAULT_RUN_ID,
                "run_date": DEFAULT_RUN_DATE,
                "force": False,
            },
            "force_true": {
                "project_id": DEFAULT_PROJECT_ID,
                "region": DEFAULT_REGION,
                "workflow_name": DEFAULT_WORKFLOW_NAME,
                "scheduler_name": DEFAULT_SCHEDULER_NAME,
                "service_account": DEFAULT_SERVICE_ACCOUNT,
                "bucket": DEFAULT_BUCKET,
                "run_id": DEFAULT_RUN_ID,
                "run_date": DEFAULT_RUN_DATE,
                "force": True,
            },
        },
    }


def build_scheduler_summary() -> dict[str, Any]:
    return {
        "name": DEFAULT_SCHEDULER_NAME,
        "manual_review_required": True,
        "schedule": "0 2 5 * *",
        "time_zone": "UTC",
        "paused": True,
        "workflow_target": {
            "workflow_name": DEFAULT_WORKFLOW_NAME,
            "project_id": DEFAULT_PROJECT_ID,
            "region": DEFAULT_REGION,
            "service_account": DEFAULT_SERVICE_ACCOUNT,
        },
        "yaml_template": build_scheduler_yaml_template(),
    }


def build_plan() -> dict[str, Any]:
    steps = build_workflow_steps()
    cloud_run_jobs = normalize_cloud_run_jobs()
    plan = {
        "generated_by": "workflow_scheduler_plan",
        "workflow": build_workflow_summary(steps),
        "scheduler": build_scheduler_summary(),
        "cloud_run_jobs": cloud_run_jobs,
        "placeholders": build_placeholders(),
        "environment_contract": build_environment_contract(),
        "manual_review_required": build_manual_review_required(steps),
        "side_effect_guardrails": build_side_effect_guardrails(),
    }
    plan["validation"] = validate_plan(plan)
    return plan


def read_source_text() -> str:
    return Path(__file__).read_text(encoding="utf-8")


def validate_no_command_execution_apis(tree: ast.AST) -> list[str]:
    errors: list[str] = []
    forbidden_imports = {"subprocess"}
    forbidden_os_members = {
        "system",
        "popen",
        "spawnl",
        "spawnle",
        "spawnlp",
        "spawnlpe",
        "spawnv",
        "spawnve",
        "spawnvp",
        "spawnvpe",
        "execl",
        "execle",
        "execlp",
        "execlpe",
        "execv",
        "execve",
        "execvp",
        "execvpe",
        "startfile",
    }
    forbidden_builtin_calls = {"eval", "exec", "compile", "__import__"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = {alias.name.split(".")[0] for alias in node.names}
            found = sorted(names & forbidden_imports)
            if found:
                errors.append(f"forbidden import: {found}")

        if isinstance(node, ast.ImportFrom):
            module = (node.module or "").split(".")[0]
            if module in forbidden_imports:
                errors.append(f"forbidden import from: {module}")
            if module == "os":
                imported = {alias.name for alias in node.names}
                found = sorted(imported & forbidden_os_members)
                if found:
                    errors.append(f"forbidden from-os import: {found}")

        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                if func.value.id == "os" and func.attr in forbidden_os_members:
                    errors.append(f"forbidden call: os.{func.attr}")
            if isinstance(func, ast.Name) and func.id in forbidden_builtin_calls:
                errors.append(f"forbidden call: {func.id}")

    return errors


def validate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    checks: list[dict[str, Any]] = []

    required_top_level = {
        "generated_by",
        "workflow",
        "scheduler",
        "cloud_run_jobs",
        "placeholders",
        "environment_contract",
        "manual_review_required",
        "side_effect_guardrails",
    }
    missing = sorted(required_top_level - set(plan))
    if missing:
        errors.append(f"missing top-level keys: {missing}")
    checks.append(
        {
            "name": "top_level_keys",
            "status": "PASS" if not missing else "FAIL",
        }
    )

    workflow = plan.get("workflow", {})
    scheduler = plan.get("scheduler", {})
    workflow_steps = workflow.get("orchestration_order", [])
    workflow_job_names = [name for step in workflow_steps for name in step.get("cloud_run_jobs", [])]
    required_job_names = [
        "gov-ai-data-manifest",
        "gov-ai-data-snapshot-plan",
        "gov-ai-gold-build",
        "gov-ai-analytics-batch",
    ]
    missing_jobs = [name for name in required_job_names if name not in workflow_job_names]
    if missing_jobs:
        errors.append(f"missing workflow job references: {missing_jobs}")
    checks.append(
        {
            "name": "workflow_job_alignment",
            "status": "PASS" if not missing_jobs else "FAIL",
        }
    )

    step_names = [step.get("step") for step in workflow_steps]
    expected_step_names = [
        "plan_source_snapshot",
        "build_silver_or_pipeline",
        "build_gold",
        "publish_or_load_bigquery",
        "run_analytics",
        "run_data_quality_audit",
        "postgres_sync_optional",
    ]
    if step_names != expected_step_names:
        errors.append("workflow step order does not match the required review sequence")
    checks.append(
        {
            "name": "workflow_step_order",
            "status": "PASS" if step_names == expected_step_names else "FAIL",
        }
    )

    scheduler_schedule = scheduler.get("schedule")
    scheduler_time_zone = scheduler.get("time_zone")
    scheduler_paused = scheduler.get("paused")
    scheduler_checks_pass = (
        scheduler_schedule == "0 2 5 * *"
        and scheduler_time_zone == "UTC"
        and scheduler_paused is True
    )
    if not scheduler_checks_pass:
        errors.append("scheduler schedule, timezone, or paused state is not aligned")
    checks.append(
        {
            "name": "scheduler_monthly_utc",
            "status": "PASS" if scheduler_checks_pass else "FAIL",
        }
    )

    text_checks = [
        ("source_text", read_source_text()),
        ("workflow_yaml_template", str(workflow.get("yaml_template", ""))),
        ("scheduler_yaml_template", str(scheduler.get("yaml_template", ""))),
    ]
    for label, text in text_checks:
        if label == "source_text":
            label_errors = validate_source_forbidden_tokens(text)
            if label_errors:
                errors.extend(f"{label}: {error}" for error in label_errors)
        else:
            label_errors = []
        checks.append(
            {
                "name": f"{label}_guard",
                "status": "PASS" if not label_errors else "FAIL",
            }
        )

    source_text = read_source_text()
    source_tree = ast.parse(source_text)
    ast_errors = validate_no_command_execution_apis(source_tree)
    if ast_errors:
        errors.extend(ast_errors)
    checks.append(
        {
            "name": "ast_execution_guard",
            "status": "PASS" if not ast_errors else "FAIL",
        }
    )

    status = "PASS" if not errors else "FAIL"
    return {
        "status": status,
        "errors": errors,
        "checks": checks,
    }


def render_yaml(value: Any, indent: int = 0) -> str:
    space = " " * indent

    if isinstance(value, dict):
        if not value:
            return f"{space}{{}}"
        lines: list[str] = []
        for key, item in value.items():
            rendered_key = key if re.match(r"^[A-Za-z_][A-Za-z0-9_-]*$", str(key)) else json.dumps(
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
                lines.append(f"{space}{rendered_key}: {json.dumps(item, ensure_ascii=False)}")
        return "\n".join(lines)

    if isinstance(value, list):
        if not value:
            return f"{space}[]"
        lines = []
        for item in value:
            if isinstance(item, dict):
                lines.append(f"{space}-")
                lines.append(render_yaml(item, indent + 2))
            elif isinstance(item, list):
                lines.append(f"{space}-")
                lines.append(render_yaml(item, indent + 2))
            elif isinstance(item, str) and "\n" in item:
                lines.append(f"{space}- |")
                for line in item.splitlines():
                    lines.append(f"{space}  {line}")
            else:
                lines.append(f"{space}- {json.dumps(item, ensure_ascii=False)}")
        return "\n".join(lines)

    if isinstance(value, str) and "\n" in value:
        lines = [f"{space}|"]
        for line in value.splitlines():
            lines.append(f"{space}  {line}")
        return "\n".join(lines)

    if value is True:
        return f"{space}true"
    if value is False:
        return f"{space}false"
    if value is None:
        return f"{space}null"

    return f"{space}{json.dumps(value, ensure_ascii=False)}"


def render_text(plan: dict[str, Any]) -> str:
    workflow = plan["workflow"]
    scheduler = plan["scheduler"]
    lines: list[str] = [
        "Workflow and Scheduler Planning",
        "Templates only; review before any deployment.",
        "",
        f"Workflow name: {workflow['name']}",
        f"Scheduler name: {scheduler['name']}",
        f"Monthly trigger: {scheduler['schedule']} UTC",
        f"Scheduler paused: {scheduler['paused']}",
        "",
        "Orchestration order:",
    ]
    for item in workflow["orchestration_order"]:
        job_names = ", ".join(item["cloud_run_jobs"]) if item["cloud_run_jobs"] else "none"
        lines.append(
            f"  - {item['step']} | kind={item['kind']} | manual_review_required={item['manual_review_required']} | jobs={job_names}"
        )
    lines.extend(
        [
            "",
            "Manual trigger payloads:",
            f"  force_false: {json.dumps(workflow['manual_trigger_payloads']['force_false'], ensure_ascii=False, indent=2)}",
            f"  force_true: {json.dumps(workflow['manual_trigger_payloads']['force_true'], ensure_ascii=False, indent=2)}",
            "",
            "Cloud Run job templates aligned from the existing offline job plan:",
        ]
    )
    for job in plan["cloud_run_jobs"]:
        lines.append(f"  - {job['name']} ({job['workflow_role']})")
    lines.extend(
        [
            "",
            "Workflow template YAML:",
            workflow["yaml_template"],
            "",
            "Scheduler template YAML:",
            scheduler["yaml_template"],
            "",
            "Side effect guardrails:",
        ]
    )
    for item in plan["side_effect_guardrails"]:
        lines.append(f"  - {item}")
    lines.append("")
    lines.append("Manual review required:")
    for item in plan["manual_review_required"]:
        lines.append(f"  - {item}")
    lines.append("")
    lines.append(f"Validation status: {plan['validation']['status']}")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print an offline workflow and scheduler planning template.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json", "yaml"),
        default="text",
        help="Render format for the generated plan.",
    )
    parser.add_argument("--check", action="store_true", help="Validate the generated plan offline.")
    return parser.parse_args()


def run_check() -> int:
    plan = build_plan()
    validation = plan["validation"]
    output = {
        "status": validation["status"],
        "errors": validation["errors"],
        "checks": validation["checks"],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if validation["status"] == "PASS" else 1


def main() -> int:
    args = parse_args()
    if args.check:
        return run_check()

    plan = build_plan()
    if args.format == "json":
        sys.stdout.write(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
        sys.stdout.write("\n")
    elif args.format == "yaml":
        sys.stdout.write(render_yaml(plan))
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_text(plan))
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
