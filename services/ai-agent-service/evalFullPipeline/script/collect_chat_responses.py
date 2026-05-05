from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any


DEFAULT_TARGET_URL = "http://localhost:3000/api/v1/ai/chat"
SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
RESULT_ROOT = PIPELINE_ROOT / "result"
CASES_PATH = SCRIPT_DIR / "cases.v1.json"
ENV_PATH = SCRIPT_DIR / ".env"
INTERNAL_TERMS = (
    "Gemini Router",
    "router",
    "parser",
    "parsedQuery",
    "AI Agent",
    "AI Agent Service",
    "database",
    "DB",
    "query planner",
    "ngrok",
    "Kaggle",
)
RETRYABLE_HTTP_STATUSES = {429, 500, 502, 503, 504}


def configure_stdio() -> None:
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
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect raw chat responses for Phase 9.1.")
    parser.add_argument("--cases", default=str(CASES_PATH))
    parser.add_argument("--target-url", default=os.getenv("EVAL_TARGET_URL", DEFAULT_TARGET_URL))
    parser.add_argument("--direct-agent-url", default=None)
    parser.add_argument("--internal-api-key", default=os.getenv("EVAL_INTERNAL_API_KEY"))
    parser.add_argument("--output-dir", default=str(RESULT_ROOT))
    parser.add_argument("--run-dir", default=None, help="Existing run dir for --resume or explicit output location.")
    parser.add_argument("--timeout-ms", type=int, default=env_int("EVAL_TIMEOUT_MS", 120000))
    parser.add_argument("--max-retries", type=int, default=env_int("EVAL_MAX_RETRIES", 3))
    parser.add_argument("--retry-backoff-ms", type=int, default=env_int("EVAL_RETRY_BACKOFF_MS", 1500))
    parser.add_argument("--sleep-ms", type=int, default=env_int("EVAL_SLEEP_MS", 300))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--continue-on-turn-failure", action="store_true")
    return parser.parse_args()


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def run_id_now() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def load_cases(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, list):
        cases = payload
    else:
        cases = payload.get("cases", [])
    if not isinstance(cases, list):
        raise ValueError("cases file must be a JSON list or an object with a 'cases' list")
    return cases


def filter_cases(cases: list[dict[str, Any]], case_ids: list[str], limit: int | None) -> list[dict[str, Any]]:
    selected = cases
    if case_ids:
        wanted = set(case_ids)
        selected = [case for case in selected if case.get("id") in wanted]
    if limit is not None:
        selected = selected[: max(limit, 0)]
    return selected


def latest_run_dir(output_dir: Path) -> Path | None:
    if not output_dir.exists():
        return None
    candidates = [path for path in output_dir.iterdir() if path.is_dir()]
    if not candidates:
        return None
    return sorted(candidates)[-1]


def prepare_run_dir(args: argparse.Namespace) -> tuple[str, Path]:
    output_root = Path(args.output_dir).resolve()
    if args.run_dir:
        run_dir = Path(args.run_dir).resolve()
        run_id = run_dir.name
    elif args.resume:
        run_dir = latest_run_dir(output_root) or output_root / run_id_now()
        run_id = run_dir.name
    else:
        run_id = run_id_now()
        run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_id, run_dir


def is_judge_target(turn_index: int, total_turns: int, target: str | None) -> bool:
    if target in (None, "last"):
        return turn_index == total_turns - 1
    if target == "all":
        return True
    try:
        return turn_index == int(target)
    except (TypeError, ValueError):
        return turn_index == total_turns - 1


def post_json(
    url: str,
    payload: dict[str, Any],
    timeout_ms: int,
    internal_api_key: str | None = None,
) -> tuple[int | None, dict[str, Any] | None, str | None, int]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
    }
    if internal_api_key:
        headers["x-internal-api-key"] = internal_api_key

    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout_ms / 1000) as response:
            raw = response.read().decode("utf-8")
            latency_ms = int((time.perf_counter() - started) * 1000)
            try:
                return response.status, json.loads(raw), None, latency_ms
            except json.JSONDecodeError as error:
                return response.status, None, f"JSON parse error: {error}", latency_ms
    except urllib.error.HTTPError as error:
        latency_ms = int((time.perf_counter() - started) * 1000)
        raw = error.read().decode("utf-8", errors="replace")
        parsed: dict[str, Any] | None = None
        parse_error: str | None = None
        if raw:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parse_error = raw[:500]
        return error.code, parsed, parse_error or error.reason, latency_ms
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return None, None, str(error), latency_ms


def should_retry(http_status: int | None, response: dict[str, Any] | None, error: str | None) -> bool:
    if error and http_status is None:
        return True
    if error and http_status and http_status < 400:
        return True
    if http_status in RETRYABLE_HTTP_STATUSES:
        return True
    if response and str(response.get("status", "")).lower() == "error":
        return True
    return False


def call_with_retries(
    url: str,
    payload: dict[str, Any],
    timeout_ms: int,
    max_retries: int,
    retry_backoff_ms: int,
    internal_api_key: str | None,
) -> dict[str, Any]:
    attempt_records: list[dict[str, Any]] = []
    final_http_status: int | None = None
    final_response: dict[str, Any] | None = None
    final_error: str | None = None
    total_latency_ms = 0

    for attempt in range(max_retries + 1):
        http_status, response, error, latency_ms = post_json(url, payload, timeout_ms, internal_api_key)
        total_latency_ms += latency_ms
        final_http_status = http_status
        final_response = response
        final_error = error
        retry = should_retry(http_status, response, error)
        attempt_records.append(
            {
                "attempt": attempt + 1,
                "http_status": http_status,
                "latency_ms": latency_ms,
                "retryable": retry,
                "error": error,
            }
        )

        if not retry or attempt >= max_retries:
            break

        delay_ms = retry_backoff_ms * (2**attempt) + random.randint(0, 250)
        print(f"Retrying attempt {attempt + 2}/{max_retries + 1} after {delay_ms} ms", flush=True)
        time.sleep(delay_ms / 1000)

    ok = (
        final_http_status is not None
        and 200 <= final_http_status < 300
        and final_response is not None
        and str(final_response.get("status", "")).lower() != "error"
    )
    return {
        "http_status": final_http_status,
        "response": final_response,
        "error": None if ok else final_error or _response_error(final_response),
        "latency_ms": total_latency_ms,
        "attempts": len(attempt_records),
        "attempt_records": attempt_records,
        "ok": ok,
    }


def _response_error(response: dict[str, Any] | None) -> str | None:
    if not response:
        return "No JSON response"
    if response.get("status") == "error":
        return str(response.get("message") or response.get("answer") or "Response status was error")
    return None


def get_nested(data: Any, path: list[str]) -> Any:
    current = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def has_rows(response: dict[str, Any] | None) -> bool:
    if not response:
        return False
    data = response.get("data")
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict) and isinstance(first.get("rows"), list) and len(first["rows"]) > 0:
            return True
    chart_data = get_nested(response, ["chart", "data"])
    return isinstance(chart_data, list) and len(chart_data) > 0


def has_internal_terms(answer: str | None) -> bool:
    if not answer:
        return False
    lower_answer = answer.lower()
    return any(term.lower() in lower_answer for term in INTERNAL_TERMS)


def compute_assertions(response: dict[str, Any] | None, expected: dict[str, Any]) -> dict[str, bool | None]:
    if not response:
        return {
            "status_matches_expected": None,
            "question_type_matches_expected": None,
            "route_matches_expected": None,
            "intent_matches_expected": None,
            "parser_debug_expected_null": None,
            "has_answer": False,
            "has_internal_terms_in_answer": False,
            "has_chart": False,
            "has_rows": False,
        }

    route = get_nested(response, ["routerDebug", "route"])
    intent = get_nested(response, ["parsedQuery", "intent"])
    parser_debug = response.get("parserDebug")
    answer = response.get("answer")
    expected_parser_null = expected.get("parserDebug") is None if "parserDebug" in expected else None

    return {
        "status_matches_expected": _matches(response.get("status"), expected.get("status")),
        "question_type_matches_expected": _matches(response.get("questionType"), expected.get("questionType")),
        "route_matches_expected": _matches(route, expected.get("route")),
        "intent_matches_expected": _matches(intent, expected.get("intent")),
        "parser_debug_expected_null": (parser_debug is None) if expected_parser_null else None,
        "has_answer": isinstance(answer, str) and bool(answer.strip()),
        "has_internal_terms_in_answer": has_internal_terms(answer if isinstance(answer, str) else None),
        "has_chart": bool(response.get("chart") and response.get("chart", {}).get("type") not in (None, "none")),
        "has_rows": has_rows(response),
    }


def _matches(actual: Any, expected: Any) -> bool | None:
    if expected is None:
        return None
    if isinstance(expected, list):
        return actual in expected
    return actual == expected


def read_existing_results(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def summarize(run_id: str, target_url: str, records: list[dict[str, Any]], total_scenarios: int) -> dict[str, Any]:
    total_turns = len(records)
    ok_records = [record for record in records if record.get("ok")]
    failed_records = [record for record in records if not record.get("ok") and not record.get("skipped")]
    skipped_records = [record for record in records if record.get("skipped")]
    latencies = [record["latency_ms"] for record in ok_records if isinstance(record.get("latency_ms"), int)]

    by_category: dict[str, dict[str, Any]] = {}
    scenarios_by_category: dict[str, set[str]] = {}
    status_counts: dict[str, int] = {}
    question_type_counts: dict[str, int] = {}
    route_counts: dict[str, int] = {}
    parser_source_counts: dict[str, int] = {}

    for record in records:
        category = record.get("category", "UNKNOWN")
        scenarios_by_category.setdefault(category, set()).add(record.get("case_id", ""))
        bucket = by_category.setdefault(
            category,
            {"scenarios": 0, "turns": 0, "ok_turns": 0, "failed_turns": 0, "skipped_turns": 0, "latencies": []},
        )
        bucket["turns"] += 1
        if record.get("ok"):
            bucket["ok_turns"] += 1
            if isinstance(record.get("latency_ms"), int):
                bucket["latencies"].append(record["latency_ms"])
        elif record.get("skipped"):
            bucket["skipped_turns"] += 1
        else:
            bucket["failed_turns"] += 1

        response = record.get("response") or {}
        _inc(status_counts, response.get("status"))
        _inc(question_type_counts, response.get("questionType"))
        _inc(route_counts, get_nested(response, ["routerDebug", "route"]))
        _inc(parser_source_counts, get_nested(response, ["parserDebug", "source"]))

    for category, bucket in by_category.items():
        bucket["scenarios"] = len(scenarios_by_category.get(category, set()))
        bucket["avg_latency_ms"] = _avg(bucket.pop("latencies"))

    return {
        "run_id": run_id,
        "target_url": target_url,
        "created_at": utc_now_iso(),
        "total_scenarios": total_scenarios,
        "total_turns": total_turns,
        "ok_turns": len(ok_records),
        "failed_turns": len(failed_records),
        "skipped_turns": len(skipped_records),
        "by_category": by_category,
        "status_counts": status_counts,
        "question_type_counts": question_type_counts,
        "route_counts": route_counts,
        "parser_source_counts": parser_source_counts,
        "avg_latency_ms": _avg(latencies),
    }


def _inc(counter: dict[str, int], key: Any) -> None:
    if key is None:
        return
    counter[str(key)] = counter.get(str(key), 0) + 1


def _avg(values: list[int]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def collect(args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    target_url = args.direct_agent_url or args.target_url
    internal_key = args.internal_api_key if args.direct_agent_url or "/agent/chat" in target_url else args.internal_api_key
    cases_path = Path(args.cases)
    cases = filter_cases(load_cases(cases_path), args.case_id, args.limit)
    run_id, run_dir = prepare_run_dir(args)

    raw_path = run_dir / "raw_results.jsonl"
    existing_records = read_existing_results(raw_path) if args.resume else []
    completed = {(record.get("case_id"), record.get("turn_index")) for record in existing_records if record.get("ok")}
    conversation_id_by_case = {
        str(record.get("case_id")): str(record.get("conversation_id"))
        for record in existing_records
        if record.get("case_id") and record.get("conversation_id")
    }
    records = list(existing_records)

    write_json(run_dir / "cases_used.json", {"cases": cases})

    for case in cases:
        case_id = str(case["id"])
        category = str(case.get("category", "UNKNOWN"))
        description = str(case.get("description", ""))
        turns = case.get("turns", [])
        if not isinstance(turns, list):
            continue
        conversation_id = conversation_id_by_case.get(case_id) or f"eval-{case_id}-{uuid.uuid4().hex[:8]}"
        conversation_id_by_case[case_id] = conversation_id
        previous_turn_failed = False

        for index, turn in enumerate(turns):
            if (case_id, index) in completed:
                continue

            expected = turn.get("expect", {}) if isinstance(turn, dict) else {}
            message = str(turn.get("message", "")) if isinstance(turn, dict) else ""
            request_context = {
                "evalCaseId": case_id,
                "evalCategory": category,
                "turnIndex": index,
            }
            base_record = {
                "run_id": run_id,
                "case_id": case_id,
                "category": category,
                "description": description,
                "conversation_id": conversation_id,
                "turn_index": index,
                "is_judge_target_turn": is_judge_target(index, len(turns), case.get("judge_target_turn")),
                "message": message,
                "expected": expected,
                "request": {
                    "url": target_url,
                    "context": request_context,
                },
                "created_at": utc_now_iso(),
            }

            if previous_turn_failed and not args.continue_on_turn_failure:
                record = {
                    **base_record,
                    "http_status": None,
                    "latency_ms": 0,
                    "attempts": 0,
                    "attempt_records": [],
                    "ok": False,
                    "skipped": True,
                    "skip_reason": "previous_turn_failed",
                    "response": None,
                    "error": "previous_turn_failed",
                    "assertions": compute_assertions(None, expected),
                }
                append_jsonl(raw_path, record)
                records.append(record)
                continue

            payload = {
                "message": message,
                "conversationId": conversation_id,
                "context": request_context,
            }
            print(f"[{case_id} turn {index}] {message}", flush=True)
            result = call_with_retries(
                url=target_url,
                payload=payload,
                timeout_ms=args.timeout_ms,
                max_retries=args.max_retries,
                retry_backoff_ms=args.retry_backoff_ms,
                internal_api_key=internal_key,
            )
            record = {
                **base_record,
                "http_status": result["http_status"],
                "latency_ms": result["latency_ms"],
                "attempts": result["attempts"],
                "attempt_records": result["attempt_records"],
                "ok": result["ok"],
                "skipped": False,
                "response": result["response"],
                "error": result["error"],
                "assertions": compute_assertions(result["response"], expected),
            }
            append_jsonl(raw_path, record)
            if not record["ok"]:
                previous_turn_failed = True
            records.append(record)

            if args.sleep_ms > 0:
                time.sleep(args.sleep_ms / 1000)

    summary = summarize(run_id, target_url, records, len(cases))
    summary["unique_case_ids"] = len({record.get("case_id") for record in records if record.get("case_id")})
    write_json(run_dir / "collect_summary.json", summary)
    return run_dir, summary


def main() -> int:
    configure_stdio()
    load_env_file(ENV_PATH)
    if ENV_PATH.exists():
        print(f"Loaded env file: {ENV_PATH}")
    args = parse_args()
    try:
        run_dir, summary = collect(args)
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(json.dumps({"run_dir": str(run_dir), **summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
