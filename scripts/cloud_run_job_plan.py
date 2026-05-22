from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_PROJECT_ID = "{project_id}"
DEFAULT_REGION = "{region}"
DEFAULT_ARTIFACT_REPOSITORY = "{artifact_repository}"
DEFAULT_SERVICE_ACCOUNT = "{service_account}"
DEFAULT_IMAGE_TAG = "{image_tag}"
DEFAULT_BUCKET = "{bucket}"
DEFAULT_RUN_ID = "{run_id}"
DEFAULT_RUN_DATE = "{run_date}"
DEFAULT_GENERATED_AT = "{generated_at}"
DEFAULT_SOURCE_NAME = "{source_name}"
DEFAULT_SOURCE_PATH = "{source_path}"
DEFAULT_PREVIOUS_MANIFEST_PATH = "{previous_manifest_path}"
DEFAULT_SILVER_OUTPUT_URI = "{silver_output_uri}"
DEFAULT_OUTPUT_DIR = "{output_dir}"
DEFAULT_OUTPUT_FORMAT = "{output_format}"
DEFAULT_POSTGRES_HOST = "{postgres_host}"
DEFAULT_POSTGRES_PORT = "{postgres_port}"
DEFAULT_POSTGRES_DB = "{postgres_db}"
DEFAULT_POSTGRES_USER = "{postgres_user}"
DEFAULT_POSTGRES_PASSWORD = "{postgres_password}"
DEFAULT_BIGQUERY_ANALYTICS_DATASET = "{bigquery_analytics_dataset}"
DEFAULT_BIGQUERY_LOCATION = "{bigquery_location}"
DEFAULT_LATEST_VALID_YEAR = "{latest_valid_year}"
DEFAULT_DATABASE_URL = "{database_url}"

FORBIDDEN_TOKENS = {
    "docker push": re.compile(r"docker\s+push", re.IGNORECASE),
    "gcloud run jobs execute": re.compile(r"gcloud\s+run\s+jobs\s+execute", re.IGNORECASE),
    "gcloud auth": re.compile(r"gcloud\s+auth", re.IGNORECASE),
    "gcloud config set": re.compile(r"gcloud\s+config\s+set", re.IGNORECASE),
    "terraform": re.compile(r"\bterraform\b", re.IGNORECASE),
    "pulumi": re.compile(r"\bpulumi\b", re.IGNORECASE),
    "gsutil": re.compile(r"\bgsutil\b", re.IGNORECASE),
    "bq": re.compile(r"\bbq\b", re.IGNORECASE),
}


def placeholder(name: str) -> str:
    return "{" + name + "}"


def repo_path(relative_path: str) -> Path:
    return REPO_ROOT / relative_path


def image_uri(
    *,
    region: str,
    project_id: str,
    artifact_repository: str,
    name: str,
    image_tag: str,
) -> str:
    return f"{region}-docker.pkg.dev/{project_id}/{artifact_repository}/{name}:{image_tag}"


def join_env_vars(items: list[tuple[str, str]]) -> str:
    return ",".join(f"{name}={value}" for name, value in items)


def join_secrets(items: list[tuple[str, str]]) -> str:
    return ",".join(f"{name}={secret_name}:latest" for name, secret_name in items)


def join_args_template(items: list[str]) -> str:
    return ",".join(items)


def render_gcloud_command(
    *,
    verb: str,
    job_name: str,
    image: str,
    region: str,
    project_id: str,
    service_account: str,
    env_vars: list[tuple[str, str]],
    secrets: list[tuple[str, str]],
    args_template: list[str],
) -> str:
    parts = [
        "gcloud",
        "run",
        "jobs",
        verb,
        job_name,
        f"--project {project_id}",
        f"--region {region}",
        f"--image {image}",
        f"--service-account {service_account}",
        "--command python",
        f"--args \"{join_args_template(args_template)}\"",
    ]

    if env_vars:
        parts.append(f"--set-env-vars {join_env_vars(env_vars)}")

    if secrets:
        parts.append(f"--set-secrets {join_secrets(secrets)}")

    return " ".join(parts)


def data_pipeline_common_env() -> list[tuple[str, str]]:
    return [
        ("RUN_ID", DEFAULT_RUN_ID),
        ("RUN_DATE", DEFAULT_RUN_DATE),
        ("OUTPUT_FORMAT", DEFAULT_OUTPUT_FORMAT),
        ("SILVER_OUTPUT_URI", DEFAULT_SILVER_OUTPUT_URI),
    ]


def build_job_templates(
    *,
    region: str,
    project_id: str,
    artifact_repository: str,
    service_account: str,
    image_tag: str,
    bucket: str,
) -> list[dict]:
    data_pipeline_image = image_uri(
        region=region,
        project_id=project_id,
        artifact_repository=artifact_repository,
        name="gov-ai-data-pipeline",
        image_tag=image_tag,
    )
    analytics_image = image_uri(
        region=region,
        project_id=project_id,
        artifact_repository=artifact_repository,
        name="gov-ai-analytics-worker",
        image_tag=image_tag,
    )

    data_manifest_args = [
        "-m",
        "jobs.build_manifest",
        "--run-id",
        DEFAULT_RUN_ID,
        "--run-date",
        DEFAULT_RUN_DATE,
        "--source",
        f"{DEFAULT_SOURCE_NAME}={DEFAULT_SOURCE_PATH}",
        "--bucket",
        bucket,
        "--generated-at",
        DEFAULT_GENERATED_AT,
        "--strict",
    ]
    data_snapshot_args = [
        "-m",
        "jobs.plan_snapshot",
        "--run-id",
        DEFAULT_RUN_ID,
        "--run-date",
        DEFAULT_RUN_DATE,
        "--bucket",
        bucket,
        "--project-id",
        project_id,
        "--source",
        f"{DEFAULT_SOURCE_NAME}={DEFAULT_SOURCE_PATH}",
        "--previous-manifest",
        DEFAULT_PREVIOUS_MANIFEST_PATH,
        "--generated-at",
        DEFAULT_GENERATED_AT,
        "--strict",
    ]
    gold_build_args = [
        "-m",
        "gold.run_gold",
        "--table",
        "all",
        "--silver",
        DEFAULT_SILVER_OUTPUT_URI,
        "--target",
        "postgres",
        "--no-reset-schema",
    ]
    analytics_batch_args = [
        "-m",
        "jobs.run_analytics",
        "--target",
        "postgres",
        "--n-clusters",
        "5",
        "--latest-valid-year",
        DEFAULT_LATEST_VALID_YEAR,
    ]

    jobs = [
        {
            "name": "gov-ai-data-manifest",
            "image_uri": data_pipeline_image,
            "create_command": render_gcloud_command(
                verb="create",
                job_name="gov-ai-data-manifest",
                image=data_pipeline_image,
                region=region,
                project_id=project_id,
                service_account=service_account,
                env_vars=[
                    ("RUN_ID", DEFAULT_RUN_ID),
                    ("RUN_DATE", DEFAULT_RUN_DATE),
                ],
                secrets=[],
                args_template=data_manifest_args,
            ),
            "update_command": render_gcloud_command(
                verb="update",
                job_name="gov-ai-data-manifest",
                image=data_pipeline_image,
                region=region,
                project_id=project_id,
                service_account=service_account,
                env_vars=[
                    ("RUN_ID", DEFAULT_RUN_ID),
                    ("RUN_DATE", DEFAULT_RUN_DATE),
                ],
                secrets=[],
                args_template=data_manifest_args,
            ),
            "args_template": data_manifest_args,
            "env": [
                "RUN_ID",
                "RUN_DATE",
                "OUTPUT_FORMAT",
                "SILVER_OUTPUT_URI",
                "BUCKET (CLI arg today; wrapper env optional)",
            ],
            "secrets": [],
            "iam": [
                "Artifact Registry Reader",
                "Logs Writer",
            ],
            "side_effect_warning": (
                "Template only. This job prints manifest JSON and must be reviewed before manual execution."
            ),
            "status": "ready_template",
        },
        {
            "name": "gov-ai-data-snapshot-plan",
            "image_uri": data_pipeline_image,
            "create_command": render_gcloud_command(
                verb="create",
                job_name="gov-ai-data-snapshot-plan",
                image=data_pipeline_image,
                region=region,
                project_id=project_id,
                service_account=service_account,
                env_vars=[
                    ("RUN_ID", DEFAULT_RUN_ID),
                    ("RUN_DATE", DEFAULT_RUN_DATE),
                ],
                secrets=[],
                args_template=data_snapshot_args,
            ),
            "update_command": render_gcloud_command(
                verb="update",
                job_name="gov-ai-data-snapshot-plan",
                image=data_pipeline_image,
                region=region,
                project_id=project_id,
                service_account=service_account,
                env_vars=[
                    ("RUN_ID", DEFAULT_RUN_ID),
                    ("RUN_DATE", DEFAULT_RUN_DATE),
                ],
                secrets=[],
                args_template=data_snapshot_args,
            ),
            "args_template": data_snapshot_args,
            "env": [
                "RUN_ID",
                "RUN_DATE",
                "OUTPUT_FORMAT",
                "SILVER_OUTPUT_URI",
                "BUCKET (CLI arg today; wrapper env optional)",
                "PROJECT_ID (CLI arg today; wrapper env optional)",
            ],
            "secrets": [],
            "iam": [
                "Artifact Registry Reader",
                "Logs Writer",
                "Storage Object Admin or narrower bucket-level write access (manual review)",
                "BigQuery Job User only if a later workflow writes ops rows (manual review)",
            ],
            "side_effect_warning": (
                "Template only. This is an offline snapshot plan and should not upload to GCS or write BigQuery."
            ),
            "status": "ready_template",
        },
        {
            "name": "gov-ai-gold-build",
            "image_uri": data_pipeline_image,
            "create_command": render_gcloud_command(
                verb="create",
                job_name="gov-ai-gold-build",
                image=data_pipeline_image,
                region=region,
                project_id=project_id,
                service_account=service_account,
                env_vars=[
                    ("RUN_ID", DEFAULT_RUN_ID),
                    ("RUN_DATE", DEFAULT_RUN_DATE),
                    ("OUTPUT_FORMAT", DEFAULT_OUTPUT_FORMAT),
                    ("SILVER_OUTPUT_URI", DEFAULT_SILVER_OUTPUT_URI),
                    ("POSTGRES_HOST", DEFAULT_POSTGRES_HOST),
                    ("POSTGRES_PORT", DEFAULT_POSTGRES_PORT),
                    ("POSTGRES_DB", DEFAULT_POSTGRES_DB),
                    ("POSTGRES_USER", DEFAULT_POSTGRES_USER),
                ],
                secrets=[
                    ("POSTGRES_PASSWORD", "POSTGRES_PASSWORD"),
                ],
                args_template=gold_build_args,
            ),
            "update_command": render_gcloud_command(
                verb="update",
                job_name="gov-ai-gold-build",
                image=data_pipeline_image,
                region=region,
                project_id=project_id,
                service_account=service_account,
                env_vars=[
                    ("RUN_ID", DEFAULT_RUN_ID),
                    ("RUN_DATE", DEFAULT_RUN_DATE),
                    ("OUTPUT_FORMAT", DEFAULT_OUTPUT_FORMAT),
                    ("SILVER_OUTPUT_URI", DEFAULT_SILVER_OUTPUT_URI),
                    ("POSTGRES_HOST", DEFAULT_POSTGRES_HOST),
                    ("POSTGRES_PORT", DEFAULT_POSTGRES_PORT),
                    ("POSTGRES_DB", DEFAULT_POSTGRES_DB),
                    ("POSTGRES_USER", DEFAULT_POSTGRES_USER),
                ],
                secrets=[
                    ("POSTGRES_PASSWORD", "POSTGRES_PASSWORD"),
                ],
                args_template=gold_build_args,
            ),
            "args_template": gold_build_args,
            "env": [
                "RUN_ID",
                "RUN_DATE",
                "OUTPUT_FORMAT",
                "SILVER_OUTPUT_URI",
                "POSTGRES_HOST",
                "POSTGRES_PORT",
                "POSTGRES_DB",
                "POSTGRES_USER",
            ],
            "secrets": [
                "POSTGRES_PASSWORD",
            ],
            "iam": [
                "Artifact Registry Reader",
                "Logs Writer",
                "Secret Manager Secret Accessor for POSTGRES_PASSWORD",
            ],
            "side_effect_warning": (
                "Template only. target=postgres will write to a live Postgres-compatible warehouse."
            ),
            "status": "ready_template",
        },
        {
            "name": "gov-ai-analytics-batch",
            "image_uri": analytics_image,
            "create_command": render_gcloud_command(
                verb="create",
                job_name="gov-ai-analytics-batch",
                image=analytics_image,
                region=region,
                project_id=project_id,
                service_account=service_account,
                env_vars=[
                    ("RUN_ID", DEFAULT_RUN_ID),
                    ("RUN_DATE", DEFAULT_RUN_DATE),
                    ("BIGQUERY_ANALYTICS_DATASET", DEFAULT_BIGQUERY_ANALYTICS_DATASET),
                    ("BIGQUERY_LOCATION", DEFAULT_BIGQUERY_LOCATION),
                    ("ANALYTICS_LATEST_VALID_YEAR", DEFAULT_LATEST_VALID_YEAR),
                ],
                secrets=[
                    ("DATABASE_URL", "DATABASE_URL"),
                ],
                args_template=analytics_batch_args,
            ),
            "update_command": render_gcloud_command(
                verb="update",
                job_name="gov-ai-analytics-batch",
                image=analytics_image,
                region=region,
                project_id=project_id,
                service_account=service_account,
                env_vars=[
                    ("RUN_ID", DEFAULT_RUN_ID),
                    ("RUN_DATE", DEFAULT_RUN_DATE),
                    ("BIGQUERY_ANALYTICS_DATASET", DEFAULT_BIGQUERY_ANALYTICS_DATASET),
                    ("BIGQUERY_LOCATION", DEFAULT_BIGQUERY_LOCATION),
                    ("ANALYTICS_LATEST_VALID_YEAR", DEFAULT_LATEST_VALID_YEAR),
                ],
                secrets=[
                    ("DATABASE_URL", "DATABASE_URL"),
                ],
                args_template=analytics_batch_args,
            ),
            "args_template": analytics_batch_args,
            "env": [
                "RUN_ID",
                "RUN_DATE",
                "BIGQUERY_ANALYTICS_DATASET",
                "BIGQUERY_LOCATION",
                "ANALYTICS_LATEST_VALID_YEAR",
            ],
            "secrets": [
                "DATABASE_URL",
            ],
            "iam": [
                "Artifact Registry Reader",
                "Logs Writer",
                "Secret Manager Secret Accessor for DATABASE_URL",
                "BigQuery Job User and dataset-level BigQuery Data Editor only if a future target=bigquery mode is enabled (manual review)",
            ],
            "side_effect_warning": (
                "Template only. target=postgres will execute live analytics writes unless changed to --dry-run."
            ),
            "status": "needs_manual_review",
        },
    ]

    return jobs


def build_plan(
    *,
    project_id: str = DEFAULT_PROJECT_ID,
    region: str = DEFAULT_REGION,
    artifact_repository: str = DEFAULT_ARTIFACT_REPOSITORY,
    service_account: str = DEFAULT_SERVICE_ACCOUNT,
    image_tag: str = DEFAULT_IMAGE_TAG,
    bucket: str = DEFAULT_BUCKET,
) -> dict:
    jobs = build_job_templates(
        region=region,
        project_id=project_id,
        artifact_repository=artifact_repository,
        service_account=service_account,
        image_tag=image_tag,
        bucket=bucket,
    )

    env_checklist = []
    secret_checklist = []
    iam_checklist = []
    for job in jobs:
        for item in job["env"]:
            if item not in env_checklist:
                env_checklist.append(item)
        for item in job["secrets"]:
            if item not in secret_checklist:
                secret_checklist.append(item)
        for item in job["iam"]:
            if item not in iam_checklist:
                iam_checklist.append(item)

    return {
        "generated_by": "cloud_run_job_plan",
        "jobs": jobs,
        "env_checklist": env_checklist,
        "secret_checklist": secret_checklist,
        "iam_checklist": iam_checklist,
        "side_effect_guardrails": [
            "Template only; review before manual execution.",
            "This generator does not execute gcloud, docker, BigQuery, GCS, or Postgres commands.",
            "No cloud resource is created, updated, deleted, or run here.",
            "No image push is performed here.",
            "Cloud Run Jobs create/update commands are templates only and must be reviewed before use.",
        ],
        "manual_review_required": [
            "services/analytics-worker/Dockerfile is missing in this repo, so the analytics image URI is template-only until a real build artifact exists.",
            "Repeated --source inputs, snapshot output paths, and later workflow wiring still need a manual deployment wrapper in the next release step.",
            "Gold build uses target=postgres and will write to live tables once executed; confirm Postgres secret wiring first.",
            "Analytics batch uses target=postgres and will write to live analytics tables once executed; confirm DATABASE_URL secret wiring and whether a future bigquery target is needed.",
        ],
    }


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
    forbidden_builtin_calls = {
        "eval",
        "exec",
        "compile",
        "__import__",
        "popen",
        "system",
    }

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


def validate_generated_plan(plan: dict) -> list[str]:
    errors: list[str] = []

    required_top_level = {
        "generated_by",
        "jobs",
        "env_checklist",
        "secret_checklist",
        "iam_checklist",
        "side_effect_guardrails",
        "manual_review_required",
    }
    missing = sorted(required_top_level - set(plan))
    if missing:
        errors.append(f"missing top-level keys: {missing}")

    if plan.get("generated_by") != "cloud_run_job_plan":
        errors.append("generated_by must be cloud_run_job_plan")

    jobs = plan.get("jobs", [])
    if not isinstance(jobs, list) or not jobs:
        errors.append("jobs must be a non-empty list")
        return errors

    forbidden_template_patterns = tuple(FORBIDDEN_TOKENS.values())
    required_job_keys = {
        "name",
        "image_uri",
        "create_command",
        "update_command",
        "args_template",
        "env",
        "secrets",
        "iam",
        "side_effect_warning",
        "status",
    }
    allowed_status = {"ready_template", "needs_manual_review"}

    for index, job in enumerate(jobs):
        if not isinstance(job, dict):
            errors.append(f"job[{index}] must be a dict")
            continue

        missing_job_keys = sorted(required_job_keys - set(job))
        if missing_job_keys:
            errors.append(f"job[{index}] missing keys: {missing_job_keys}")

        if job.get("status") not in allowed_status:
            errors.append(f"job[{index}] has invalid status: {job.get('status')!r}")

        name = str(job.get("name", ""))
        image_uri_value = str(job.get("image_uri", ""))
        if not name.startswith("gov-ai-"):
            errors.append(f"job[{index}] has unexpected name: {name!r}")
        if not image_uri_value:
            errors.append(f"job[{index}] missing image_uri")

        command_fields = ("create_command", "update_command")
        for key in command_fields:
            value = str(job.get(key, ""))
            lowered = value.lower()
            for pattern in forbidden_template_patterns:
                if pattern.search(lowered):
                    errors.append(f"job[{index}].{key} contains forbidden command text")

        args_value = job.get("args_template")
        if isinstance(args_value, list):
            args_text = " ".join(str(item) for item in args_value)
        elif isinstance(args_value, str):
            args_text = args_value
        else:
            errors.append(f"job[{index}] args_template must be a list or string")
            args_text = ""

        lowered_args = args_text.lower()
        for pattern in forbidden_template_patterns:
            if pattern.search(lowered_args):
                errors.append(f"job[{index}].args_template contains forbidden command text")

    return errors


def validate_name_safety(plan: dict) -> list[str]:
    errors: list[str] = []
    labels = []
    for job in plan.get("jobs", []):
        labels.append(str(job.get("name", "")))
        labels.append(str(job.get("image_uri", "")))

    compact_label_pattern = re.compile(r"\b\d+[A-Z]\b")
    for value in labels:
        if compact_label_pattern.search(value):
            errors.append(f"unsafe compact label found in generated output: {value!r}")

    return errors


def run_check() -> int:
    errors: list[str] = []

    source = read_source_text()
    tree = ast.parse(source)
    errors.extend(validate_no_command_execution_apis(tree))

    plan = build_plan()
    errors.extend(validate_generated_plan(plan))
    errors.extend(validate_name_safety(plan))

    if errors:
        print("cloud_run_job_plan check failed")
        for error in errors:
            print(f"- {error}")
        return 1

    print("cloud_run_job_plan check passed")
    return 0


def render_text(plan: dict) -> str:
    lines: list[str] = []
    lines.append("Cloud Run Jobs Command Templates")
    lines.append("Template only; review before manual execution.")
    lines.append("")

    for job in plan["jobs"]:
        lines.append(f"Job: {job['name']}")
        lines.append(f"  Status: {job['status']}")
        lines.append(f"  Image: {job['image_uri']}")
        lines.append("  Create command:")
        lines.append(f"    {job['create_command']}")
        lines.append("  Update command:")
        lines.append(f"    {job['update_command']}")
        lines.append("  Args template:")
        if isinstance(job["args_template"], list):
            for item in job["args_template"]:
                lines.append(f"    - {item}")
        else:
            lines.append(f"    {job['args_template']}")
        lines.append("  Env checklist:")
        for item in job["env"]:
            lines.append(f"    - {item}")
        lines.append("  Secret checklist:")
        if job["secrets"]:
            for item in job["secrets"]:
                lines.append(f"    - {item}")
        else:
            lines.append("    - none")
        lines.append("  IAM checklist:")
        for item in job["iam"]:
            lines.append(f"    - {item}")
        lines.append(f"  Side effect warning: {job['side_effect_warning']}")
        lines.append("")

    lines.append("Top-level env checklist:")
    for item in plan["env_checklist"]:
        lines.append(f"  - {item}")
    lines.append("Top-level secret checklist:")
    for item in plan["secret_checklist"]:
        lines.append(f"  - {item}")
    lines.append("Top-level IAM checklist:")
    for item in plan["iam_checklist"]:
        lines.append(f"  - {item}")
    lines.append("Side effect guardrails:")
    for item in plan["side_effect_guardrails"]:
        lines.append(f"  - {item}")
    lines.append("Manual review required:")
    for item in plan["manual_review_required"]:
        lines.append(f"  - {item}")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print offline Cloud Run Jobs command templates and checklists.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Render format for the generated plan.",
    )
    parser.add_argument("--check", action="store_true", help="Validate the plan offline.")
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--artifact-repository", default=DEFAULT_ARTIFACT_REPOSITORY)
    parser.add_argument("--service-account", default=DEFAULT_SERVICE_ACCOUNT)
    parser.add_argument("--image-tag", default=DEFAULT_IMAGE_TAG)
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.check:
        return run_check()

    plan = build_plan(
        project_id=args.project_id,
        region=args.region,
        artifact_repository=args.artifact_repository,
        service_account=args.service_account,
        image_tag=args.image_tag,
        bucket=args.bucket,
    )

    if args.format == "json":
        sys.stdout.write(json.dumps(plan, ensure_ascii=False, indent=2))
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_text(plan))
        sys.stdout.write("\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
