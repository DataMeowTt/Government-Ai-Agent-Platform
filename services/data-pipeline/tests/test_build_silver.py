from __future__ import annotations

import json
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
PIPELINE_DIR = REPO_ROOT / "services" / "data-pipeline"


def _run_build(args: list[str]) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.setdefault("PYSPARK_PYTHON", sys.executable)
    env.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)
    return subprocess.run(
        [sys.executable, "-m", "jobs.build_silver", *args],
        cwd=PIPELINE_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_build_silver_help() -> None:
    result = _run_build(["--help"])
    assert result.returncode == 0
    assert "Build local silver_indicators" in result.stdout


def test_build_silver_fixture_csv(tmp_path: Path) -> None:
    if importlib.util.find_spec("pyspark") is None:
        pytest.skip("pyspark is not installed in current environment")
    out_dir = tmp_path / "silver"
    result = _run_build(
        [
            "--source",
            "all",
            "--run-id",
            "silver-fixture-test",
            "--run-date",
            "2026-05-18",
            "--output-dir",
            str(out_dir),
            "--output-format",
            "csv",
            "--spark-master",
            "local[1]",
            "--fixture",
        ]
    )
    assert result.returncode == 0, result.stderr
    manifest = json.loads((out_dir / "silver_manifest.json").read_text(encoding="utf-8"))
    assert manifest["validation_summary"]["row_count"] > 0
    assert (out_dir / "silver_indicators").exists()
