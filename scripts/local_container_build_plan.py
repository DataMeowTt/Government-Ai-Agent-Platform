from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

DATA_PIPELINE = {
    "service": "data-pipeline",
    "implemented": True,
    "image": "gov-ai-data-pipeline:local",
    "context": "services/data-pipeline",
    "dockerfile": "services/data-pipeline/Dockerfile",
    "dockerignore": "services/data-pipeline/.dockerignore",
    "safe_default_command": 'CMD ["python", "-m", "jobs.plan_snapshot", "--help"]',
    "build_command": (
        "docker build -f services/data-pipeline/Dockerfile "
        "-t gov-ai-data-pipeline:local services/data-pipeline"
    ),
    "run_command": "docker run --rm gov-ai-data-pipeline:local",
    "run_help_command": (
        "docker run --rm gov-ai-data-pipeline:local "
        "python -m jobs.plan_snapshot --help"
    ),
    "expected_files": [
        "services/data-pipeline/Dockerfile",
        "services/data-pipeline/.dockerignore",
        "services/data-pipeline/pyproject.toml",
        "services/data-pipeline/jobs/plan_snapshot.py",
    ],
}

ANALYTICS_WORKER = {
    "service": "analytics-worker",
    "implemented": False,
    "image": "gov-ai-analytics-worker:local",
    "context": "services/analytics-worker",
    "dockerfile": "services/analytics-worker/Dockerfile",
    "dockerignore": "services/analytics-worker/.dockerignore",
    "expected_files": [
        "services/analytics-worker/requirements.txt",
        "services/analytics-worker/src/jobs/run_analytics.py",
    ],
    "limitation": (
        "services/analytics-worker/requirements.txt exists, but "
        "services/analytics-worker/src/jobs/run_analytics.py is missing, so the "
        "analytics-worker Dockerfile is not created in this local plan."
    ),
}

FORBIDDEN_PATTERNS = {
    "gcloud": re.compile(r"\bgcloud\b", re.IGNORECASE),
    "bq": re.compile(r"\bbq\b", re.IGNORECASE),
    "gsutil": re.compile(r"\bgsutil\b", re.IGNORECASE),
    "docker push": re.compile(r"docker\s+push", re.IGNORECASE),
    "artifact registry": re.compile(r"artifact\s+registry", re.IGNORECASE),
    "cloud run": re.compile(r"cloud\s+run", re.IGNORECASE),
    "cloud run jobs": re.compile(r"cloud\s+run\s+jobs", re.IGNORECASE),
}

SAFE_CMD_PATTERNS = (
    "--help",
    "dry-run",
    "dry_run",
    "plan_snapshot",
)


def repo_path(relative_path: str) -> Path:
    return REPO_ROOT / relative_path


def build_plan() -> dict:
    return {
        "plan_name": "local-container-build-plan",
        "purpose": "Local Dockerfile and offline build/run command plan only.",
        "cloud_side_effect_guard": (
            "This plan does not create cloud resources, does not push images, and "
            "does not run managed jobs. Commands are local Docker build/run helpers only."
        ),
        "services": [
            DATA_PIPELINE,
            ANALYTICS_WORKER,
        ],
    }


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def check_file_exists(relative_path: str, errors: list[str]) -> None:
    if not repo_path(relative_path).exists():
        errors.append(f"missing expected file: {relative_path}")


def check_no_forbidden_commands(relative_path: str, errors: list[str]) -> None:
    path = repo_path(relative_path)
    if not path.exists():
        return

    text = read_text(path)
    for label, pattern in FORBIDDEN_PATTERNS.items():
        if pattern.search(text):
            errors.append(f"unsafe marker found in {relative_path}: {label}")


def check_safe_default_command(relative_path: str, errors: list[str]) -> None:
    path = repo_path(relative_path)
    if not path.exists():
        return

    text = read_text(path)
    command_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip().upper().startswith(("CMD", "ENTRYPOINT"))
    ]
    if not command_lines:
        errors.append(f"missing CMD/ENTRYPOINT in {relative_path}")
        return

    default_command = command_lines[-1].lower()
    if not any(marker in default_command for marker in SAFE_CMD_PATTERNS):
        errors.append(f"default command is not obviously safe/help/dry-run: {relative_path}")


def run_check() -> int:
    errors: list[str] = []

    for relative_path in DATA_PIPELINE["expected_files"]:
        check_file_exists(relative_path, errors)

    for relative_path in (
        DATA_PIPELINE["dockerfile"],
        DATA_PIPELINE["dockerignore"],
    ):
        check_no_forbidden_commands(relative_path, errors)

    check_safe_default_command(DATA_PIPELINE["dockerfile"], errors)

    analytics_cli = repo_path("services/analytics-worker/src/jobs/run_analytics.py")
    analytics_dockerfile = repo_path(ANALYTICS_WORKER["dockerfile"])
    analytics_dockerignore = repo_path(ANALYTICS_WORKER["dockerignore"])
    if analytics_dockerfile.exists() or analytics_dockerignore.exists():
        for relative_path in (
            ANALYTICS_WORKER["dockerfile"],
            ANALYTICS_WORKER["dockerignore"],
        ):
            check_file_exists(relative_path, errors)
            check_no_forbidden_commands(relative_path, errors)
        check_safe_default_command(ANALYTICS_WORKER["dockerfile"], errors)
        if not analytics_cli.exists():
            errors.append("analytics-worker Dockerfile exists but safe CLI is missing.")

    result = {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "analytics_worker_implemented": analytics_dockerfile.exists(),
        "analytics_worker_limitation": ANALYTICS_WORKER["limitation"],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not errors else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print or validate the local container build plan."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate required local container files and safety markers.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.check:
        return run_check()

    print(json.dumps(build_plan(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
