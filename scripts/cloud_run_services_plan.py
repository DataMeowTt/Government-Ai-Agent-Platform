from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLOUD_RUN_DIR = ROOT / "infra" / "gcp" / "cloud-run"

SECRET_BINDINGS = {
    "AI_AGENT_INTERNAL_API_KEY": "gov-ai-agent-internal-api-key",
    "GEMINI_API_KEY": "gov-ai-gemini-api-key",
    "PARSER_SERVICE_BASE_URL": "gov-ai-parser-service-base-url",
    "PARSER_SERVICE_API_KEY": "gov-ai-parser-service-api-key",
}


@dataclass
class LoadedConfig:
    deploy: dict[str, str]
    backend: dict[str, str]
    ai_agent: dict[str, str]
    deploy_file: Path
    backend_file: Path
    ai_agent_file: Path


def _resolve_env_file(name: str) -> Path:
    local_file = CLOUD_RUN_DIR / f"{name}.env.local"
    example_file = CLOUD_RUN_DIR / f"{name}.env.example"
    if local_file.exists():
        return local_file
    if example_file.exists():
        return example_file
    raise FileNotFoundError(f"Missing env file for {name}: {local_file} or {example_file}")


def _load_env(path: Path) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        parsed[key.strip()] = value.strip().strip('"').strip("'")
    return parsed


def _run_read_only(command: list[str]) -> tuple[bool, str]:
    try:
        out = subprocess.check_output(command, text=True, encoding="utf-8", stderr=subprocess.STDOUT)
        return True, out.strip()
    except Exception as exc:  # pragma: no cover
        return False, str(exc)


def load_config() -> LoadedConfig:
    deploy_file = _resolve_env_file("deploy")
    backend_file = _resolve_env_file("backend")
    ai_agent_file = _resolve_env_file("ai-agent")
    return LoadedConfig(
        deploy=_load_env(deploy_file),
        backend=_load_env(backend_file),
        ai_agent=_load_env(ai_agent_file),
        deploy_file=deploy_file,
        backend_file=backend_file,
        ai_agent_file=ai_agent_file,
    )


def build_plan(config: LoadedConfig, include_cloud_checks: bool) -> dict:
    project_id = config.deploy.get("PROJECT_ID", "")
    region = config.deploy.get("REGION", "")
    artifact_repository = config.deploy.get("ARTIFACT_REPOSITORY", "")
    image_tag = config.deploy.get("IMAGE_TAG", "")
    backend_image_name = config.deploy.get("BACKEND_IMAGE_NAME", "")
    ai_agent_image_name = config.deploy.get("AI_AGENT_IMAGE_NAME", "")
    backend_service_name = config.deploy.get("BACKEND_SERVICE_NAME", "")
    ai_agent_service_name = config.deploy.get("AI_AGENT_SERVICE_NAME", "")

    backend_image = (
        f"{region}-docker.pkg.dev/{project_id}/{artifact_repository}/{backend_image_name}:{image_tag}"
    )
    ai_agent_image = (
        f"{region}-docker.pkg.dev/{project_id}/{artifact_repository}/{ai_agent_image_name}:{image_tag}"
    )

    scheduler_command = (
        "gcloud scheduler jobs describe economic-data-pipeline-monthly "
        f"--location {region} --project {project_id} --format=value(state)"
    )

    plan = {
        "env_files": {
            "deploy": str(config.deploy_file),
            "backend": str(config.backend_file),
            "ai_agent": str(config.ai_agent_file),
        },
        "deploy_context": {
            "project_id": project_id,
            "region": region,
            "backend_service_name": backend_service_name,
            "ai_agent_service_name": ai_agent_service_name,
            "runtime_service_account": config.deploy.get("RUNTIME_SERVICE_ACCOUNT", ""),
            "backend_image": backend_image,
            "ai_agent_image": ai_agent_image,
        },
        "non_secret_env": {
            "backend": config.backend,
            "ai_agent": config.ai_agent,
        },
        "secret_bindings": {
            "backend": {
                "AI_AGENT_INTERNAL_API_KEY": "gov-ai-agent-internal-api-key:latest",
            },
            "ai_agent": {
                "INTERNAL_API_KEY": "gov-ai-agent-internal-api-key:latest",
                "GEMINI_API_KEY": "gov-ai-gemini-api-key:latest",
                "PARSER_SERVICE_BASE_URL": "gov-ai-parser-service-base-url:latest (optional)",
                "PARSER_SERVICE_API_KEY": "gov-ai-parser-service-api-key:latest (optional if runtime uses parser API key)",
            },
        },
        "scheduler_verification": {
            "command": scheduler_command,
            "state": "not verified",
        },
        "secret_existence": {
            name: "not verified" for name in SECRET_BINDINGS.values()
        },
        "guardrails": [
            "Plan output is sanitized and never includes secret values.",
            "Use --set-env-vars for non-secret values only.",
            "Use --set-secrets for secret bindings only.",
            "Scheduler must remain PAUSED.",
        ],
    }

    if include_cloud_checks:
        ok, active_project = _run_read_only(["gcloud", "config", "get-value", "project"])
        plan["active_project"] = active_project if ok else "not verified"

        sched_ok, sched_state = _run_read_only(
            [
                "gcloud",
                "scheduler",
                "jobs",
                "describe",
                "economic-data-pipeline-monthly",
                "--location",
                region,
                "--project",
                project_id,
                "--format=value(state)",
            ]
        )
        plan["scheduler_verification"]["state"] = sched_state if sched_ok else "not verified"

        for secret_name in SECRET_BINDINGS.values():
            secret_ok, _ = _run_read_only(
                ["gcloud", "secrets", "describe", secret_name, "--project", project_id]
            )
            plan["secret_existence"][secret_name] = "present" if secret_ok else "missing"

    return plan


def main() -> None:
    parser = argparse.ArgumentParser(description="Cloud Run services sanitized deploy plan")
    parser.add_argument(
        "--no-cloud-checks",
        action="store_true",
        help="Do not run read-only gcloud checks.",
    )
    args = parser.parse_args()

    cfg = load_config()
    plan = build_plan(cfg, include_cloud_checks=not args.no_cloud_checks)
    print(json.dumps(plan, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
