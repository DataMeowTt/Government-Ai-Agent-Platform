from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_parser_catalog_audit_reports_stale_indicators() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    script_path = repo_root / "scripts" / "parser_catalog_audit.py"

    completed = subprocess.run(
        [sys.executable, str(script_path), "--format", "json"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    report = json.loads(completed.stdout)

    assert report["parser_artifact_available"] is True
    parser_only = set(report["indicator_drift"]["parser_only_indicators"])
    assert "decade" in parser_only
    assert "flag_score" in parser_only
