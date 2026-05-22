from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
RESULT_ROOT = PIPELINE_ROOT / "result"
CASES_PATH = SCRIPT_DIR / "cases.v1.json"
ENV_PATH = SCRIPT_DIR / ".env"
COLLECT_SCRIPT = SCRIPT_DIR / "collect_chat_responses.py"
JUDGE_SCRIPT = SCRIPT_DIR / "judge_chat_responses.py"


def configure_stdio() -> None:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def run_id_now() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run full chat quality eval pipeline.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--target-url", default=None)
    parser.add_argument("--direct-agent-url", default=None)
    parser.add_argument("--skip-collect", action="store_true")
    parser.add_argument("--skip-judge", action="store_true")
    parser.add_argument("--resume-run-id", default=None)
    parser.add_argument("--collect-max-passes", type=int, default=env_int("EVAL_PIPELINE_COLLECT_MAX_PASSES", 3))
    return parser.parse_args()


def load_cases() -> list[dict[str, Any]]:
    payload = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    cases = payload.get("cases", payload) if isinstance(payload, dict) else payload
    if not isinstance(cases, list):
        raise ValueError("cases.v1.json must contain a list or object with cases list")
    return cases


def selected_case_ids(cases: list[dict[str, Any]], case_ids: list[str], limit: int | None) -> set[str]:
    selected = cases
    if case_ids:
        wanted = set(case_ids)
        selected = [case for case in selected if case.get("id") in wanted]
    if limit is not None:
        selected = selected[: max(limit, 0)]
    return {str(case.get("id")) for case in selected}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            records.append(item)
    return records


def target_turns_ok(records: list[dict[str, Any]], expected_ids: set[str]) -> bool:
    by_case: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        case_id = str(record.get("case_id") or "")
        if case_id in expected_ids:
            by_case.setdefault(case_id, []).append(record)
    for case_id in expected_ids:
        turns = sorted(by_case.get(case_id, []), key=lambda item: int(item.get("turn_index", 0)))
        if not turns:
            return False
        target = next((turn for turn in reversed(turns) if turn.get("is_judge_target_turn")), turns[-1])
        if target.get("skipped") or not target.get("ok"):
            return False
    return True


def collect_is_full(run_dir: Path, expected_ids: set[str]) -> tuple[bool, dict[str, Any]]:
    records = read_jsonl(run_dir / "raw_results.jsonl")
    unique_ids = {str(record.get("case_id")) for record in records if record.get("case_id")}
    ok = expected_ids.issubset(unique_ids) and target_turns_ok(records, expected_ids)
    return ok, {
        "total_turns": len(records),
        "unique_case_ids": len(unique_ids),
        "expected_scenarios": len(expected_ids),
        "target_turns_ok": target_turns_ok(records, expected_ids),
    }


def run_command(command: list[str]) -> int:
    print("Running:", " ".join(command))
    return subprocess.run(command, cwd=str(SCRIPT_DIR), check=False).returncode


def main() -> int:
    configure_stdio()
    load_env_file(ENV_PATH)
    if ENV_PATH.exists():
        print(f"Loaded env file: {ENV_PATH}")
    args = parse_args()

    if not CASES_PATH.exists():
        print(f"Missing cases file: {CASES_PATH}")
        return 1

    run_id = args.resume_run_id or args.run_id or run_id_now()
    run_dir = RESULT_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    cases = load_cases()
    expected_ids = selected_case_ids(cases, args.case_id, args.limit)

    collect_summary: dict[str, Any] = {}
    collect_ok = False

    if not args.skip_collect:
        for collect_pass in range(1, max(args.collect_max_passes, 1) + 1):
            command = [
                sys.executable,
                str(COLLECT_SCRIPT),
                "--cases",
                str(CASES_PATH),
                "--run-dir",
                str(run_dir),
                "--output-dir",
                str(RESULT_ROOT),
            ]
            if collect_pass > 1 or args.resume_run_id:
                command.append("--resume")
            if args.limit is not None:
                command.extend(["--limit", str(args.limit)])
            for case_id in args.case_id:
                command.extend(["--case-id", case_id])
            if args.target_url:
                command.extend(["--target-url", args.target_url])
            if args.direct_agent_url:
                command.extend(["--direct-agent-url", args.direct_agent_url])

            code = run_command(command)
            collect_ok, collect_summary = collect_is_full(run_dir, expected_ids)
            print(f"Collect pass {collect_pass}: code={code}, full={collect_ok}, summary={collect_summary}")
            if collect_ok:
                break
        if not collect_ok:
            print("Collect did not complete all expected target turns; judge skipped.")
            print_final(run_id, run_dir, collect_ok, collect_summary, None)
            return 1
    else:
        collect_ok, collect_summary = collect_is_full(run_dir, expected_ids)
        if not collect_ok:
            print("Existing collect result is not full; judge skipped.")
            print_final(run_id, run_dir, collect_ok, collect_summary, None)
            return 1

    judge_summary = None
    if not args.skip_judge:
        command = [
            sys.executable,
            str(JUDGE_SCRIPT),
            "--run-dir",
            str(run_dir),
            "--output",
            str(run_dir / "judge_results.json"),
            "--overwrite",
        ]
        if args.limit is not None:
            command.extend(["--limit", str(args.limit)])
        for case_id in args.case_id:
            command.extend(["--case-id", case_id])
        code = run_command(command)
        judge_path = run_dir / "judge_results.json"
        if code == 0 and judge_path.exists():
            judge_payload = json.loads(judge_path.read_text(encoding="utf-8"))
            judge_summary = judge_payload.get("summary")
        else:
            print(f"Judge failed or did not write output: code={code}")
            print_final(run_id, run_dir, collect_ok, collect_summary, None)
            return 1

    print_final(run_id, run_dir, collect_ok, collect_summary, judge_summary)
    return 0


def print_final(
    run_id: str,
    run_dir: Path,
    collect_ok: bool,
    collect_summary: dict[str, Any],
    judge_summary: dict[str, Any] | None,
) -> None:
    print("")
    print("PIPELINE SUMMARY")
    print(f"run_id: {run_id}")
    print(f"collect: {'ok' if collect_ok else 'failed'}")
    print(f"total_scenarios: {collect_summary.get('expected_scenarios')}")
    print(f"total_turns: {collect_summary.get('total_turns')}")
    if judge_summary:
        print(f"judge pass/warning/fail/blocked: {judge_summary.get('pass')}/{judge_summary.get('warning')}/{judge_summary.get('fail')}/{judge_summary.get('blocked')}")
        print(f"avg_score: {judge_summary.get('avg_score')}")
    print(f"result path: {run_dir}")


if __name__ == "__main__":
    raise SystemExit(main())
