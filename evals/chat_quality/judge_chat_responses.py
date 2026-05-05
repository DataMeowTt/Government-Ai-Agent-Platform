from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import re
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_MODEL = "gemini-3.1-flash-lite-preview"
DEFAULT_RUN_ROOT = Path("eval_runs/chat_quality")
DEFAULT_RUBRIC_PATH = Path("evals/chat_quality/judge_rubric.v1.md")
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
    "model parser",
    "ngrok",
    "Kaggle",
)
RETRYABLE_HTTP = {429, 500, 502, 503, 504}


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Judge collected chat responses with Gemini.")
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--raw-results", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--model", default=os.getenv("EVAL_GEMINI_MODEL", DEFAULT_MODEL))
    parser.add_argument("--api-keys", default=os.getenv("EVAL_GEMINI_API_KEYS") or os.getenv("GEMINI_API_KEY") or "")
    parser.add_argument("--timeout-ms", type=int, default=env_int("EVAL_JUDGE_TIMEOUT_MS", 30000))
    parser.add_argument("--max-retries", type=int, default=env_int("EVAL_JUDGE_MAX_RETRIES", 3))
    parser.add_argument("--retry-backoff-ms", type=int, default=env_int("EVAL_JUDGE_RETRY_BACKOFF_MS", 1500))
    parser.add_argument("--sleep-ms", type=int, default=env_int("EVAL_JUDGE_SLEEP_MS", 500))
    parser.add_argument("--concurrency", type=int, default=env_int("EVAL_JUDGE_CONCURRENCY", 1))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--retry-errors", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--rubric", default=str(DEFAULT_RUBRIC_PATH))
    return parser.parse_args()


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def judge_run_id() -> str:
    return "judge_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def latest_run_dir() -> Path | None:
    if not DEFAULT_RUN_ROOT.exists():
        return None
    candidates = [path for path in DEFAULT_RUN_ROOT.iterdir() if (path / "raw_results.jsonl").exists()]
    if not candidates:
        return None
    return sorted(candidates)[-1]


def resolve_paths(args: argparse.Namespace) -> tuple[Path | None, Path | None, Path | None]:
    run_dir = Path(args.run_dir) if args.run_dir else None
    if run_dir is None and args.raw_results is None:
        run_dir = latest_run_dir()
    raw_results = Path(args.raw_results) if args.raw_results else (run_dir / "raw_results.jsonl" if run_dir else None)
    output_dir = Path(args.output_dir) if args.output_dir else run_dir
    return run_dir, raw_results, output_dir


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {error}") from error
            if isinstance(record, dict):
                records.append(record)
    return records


def group_by_case(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(str(record.get("case_id", "")), []).append(record)
    for turns in grouped.values():
        turns.sort(key=lambda item: int(item.get("turn_index", 0)))
    return grouped


def select_cases(grouped: dict[str, list[dict[str, Any]]], case_ids: list[str], limit: int | None) -> list[tuple[str, list[dict[str, Any]]]]:
    items = [(case_id, turns) for case_id, turns in sorted(grouped.items()) if case_id]
    if case_ids:
        wanted = set(case_ids)
        items = [(case_id, turns) for case_id, turns in items if case_id in wanted]
    if limit is not None:
        items = items[: max(limit, 0)]
    return items


def pick_target_turn(turns: list[dict[str, Any]]) -> dict[str, Any] | None:
    flagged = [turn for turn in turns if turn.get("is_judge_target_turn")]
    if flagged:
        return flagged[-1]
    candidates = [turn for turn in turns if not turn.get("skipped")]
    if candidates:
        return candidates[-1]
    return None


def get_nested(value: Any, path: list[str]) -> Any:
    current = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def value_matches(actual: Any, expected: Any) -> bool | None:
    if expected is None:
        return None
    if isinstance(expected, list):
        return actual in expected
    return actual == expected


def has_internal_terms(answer: str | None) -> bool:
    if not answer:
        return False
    lower_answer = answer.lower()
    return any(term.lower() in lower_answer for term in INTERNAL_TERMS)


def has_rows(response: dict[str, Any] | None) -> bool:
    if not response:
        return False
    data = response.get("data")
    if isinstance(data, list) and data:
        rows = data[0].get("rows") if isinstance(data[0], dict) else None
        if isinstance(rows, list) and rows:
            return True
    chart_data = get_nested(response, ["chart", "data"])
    return isinstance(chart_data, list) and bool(chart_data)


def has_chart(response: dict[str, Any] | None) -> bool:
    chart = response.get("chart") if response else None
    return isinstance(chart, dict) and chart.get("type") not in (None, "none")


def expected_value(expected: dict[str, Any], key: str) -> Any:
    return expected.get(key) if isinstance(expected, dict) else None


def nam_false_positive(response: dict[str, Any] | None, target_message: str) -> bool:
    if "việt nam" not in target_message.lower() and "viet nam" not in target_message.lower():
        return False
    countries = get_nested(response, ["metadata", "countries"])
    parsed_countries = get_nested(response, ["parsedQuery", "countries"])
    all_countries: list[Any] = []
    if isinstance(countries, list):
        all_countries.extend(countries)
    if isinstance(parsed_countries, list):
        all_countries.extend(parsed_countries)
    return "NAM" in {str(country).upper() for country in all_countries}


def compute_rule_checks(target: dict[str, Any] | None) -> dict[str, Any]:
    if target is None:
        return {
            "has_answer": False,
            "no_internal_terms": True,
            "status_matches_expected": None,
            "question_type_matches_expected": None,
            "route_matches_expected": None,
            "intent_matches_expected": None,
            "start_year_matches_expected": None,
            "end_year_matches_expected": None,
            "limit_matches_expected": None,
            "parser_debug_null_expected": None,
            "has_chart": False,
            "has_rows": False,
            "nam_false_positive": False,
            "latency_ms": None,
        }

    response = target.get("response") if isinstance(target.get("response"), dict) else {}
    expected = target.get("expected") if isinstance(target.get("expected"), dict) else {}
    answer = response.get("answer")
    parsed = response.get("parsedQuery") if isinstance(response.get("parsedQuery"), dict) else {}
    route = get_nested(response, ["routerDebug", "route"])
    parser_debug = response.get("parserDebug")

    return {
        "has_answer": isinstance(answer, str) and bool(answer.strip()),
        "no_internal_terms": not has_internal_terms(answer if isinstance(answer, str) else None),
        "status_matches_expected": value_matches(response.get("status"), expected_value(expected, "status")),
        "question_type_matches_expected": value_matches(response.get("questionType"), expected_value(expected, "questionType")),
        "route_matches_expected": value_matches(route, expected_value(expected, "route")),
        "intent_matches_expected": value_matches(parsed.get("intent"), expected_value(expected, "intent")),
        "start_year_matches_expected": value_matches(parsed.get("start_year"), expected_value(expected, "start_year")),
        "end_year_matches_expected": value_matches(parsed.get("end_year"), expected_value(expected, "end_year")),
        "limit_matches_expected": value_matches(parsed.get("limit"), expected_value(expected, "limit")),
        "parser_debug_null_expected": (parser_debug is None) if "parserDebug" in expected and expected["parserDebug"] is None else None,
        "has_chart": has_chart(response),
        "has_rows": has_rows(response),
        "nam_false_positive": nam_false_positive(response, str(target.get("message", ""))),
        "latency_ms": target.get("latency_ms"),
    }


def clear_clarifying_question(response: dict[str, Any]) -> bool:
    questions = response.get("clarificationQuestions")
    if isinstance(questions, list) and len(questions) > 0:
        return True
    answer = str(response.get("answer") or "")
    return "?" in answer or any(token in answer.lower() for token in ("bạn muốn", "vui lòng", "cần", "chỉ số", "quốc gia", "năm"))


def hard_block_reasons(target: dict[str, Any] | None, rule_checks: dict[str, Any], judge_score: float | None = None) -> list[str]:
    if target is None:
        return ["NO_VALID_TARGET_TURN"]
    response = target.get("response") if isinstance(target.get("response"), dict) else {}
    expected = target.get("expected") if isinstance(target.get("expected"), dict) else {}
    category = str(target.get("category", ""))
    reasons: list[str] = []

    if not target.get("ok"):
        reasons.append("HTTP_OR_TARGET_TURN_FAILED")
    if not rule_checks.get("has_answer") and response.get("status") != "error":
        reasons.append("EMPTY_ANSWER")
    if not rule_checks.get("no_internal_terms"):
        reasons.append("INTERNAL_TERMS_IN_ANSWER")

    expected_status = expected.get("status")
    actual_status = response.get("status")
    if expected_status == "success" and actual_status in {"needs_clarification", "off_topic", "unsupported"}:
        reasons.append("DATA_QUERY_EXPECTED_SUCCESS_BUT_STOPPED")

    route = get_nested(response, ["routerDebug", "route"])
    if category == "FOLLOW_UP_ANALYSIS":
        if response.get("parserDebug") is not None or get_nested(response, ["routerDebug", "needs_parser"]) is True or get_nested(response, ["routerDebug", "needs_db"]) is True:
            reasons.append("FOLLOW_UP_ANALYSIS_USED_PARSER_OR_DB")
    if category == "FOLLOW_UP_MODIFY_QUERY" and route != "FOLLOW_UP_MODIFY_QUERY":
        reasons.append("FOLLOW_UP_MODIFY_ROUTE_MISMATCH")
    if category == "NEED_CLARIFICATION" and not clear_clarifying_question(response):
        reasons.append("NEED_CLARIFICATION_WITHOUT_QUESTION")
    if category == "UNSUPPORTED_OFF_TOPIC" and actual_status == "success" and get_nested(response, ["routerDebug", "needs_db"]) is True:
        reasons.append("UNSUPPORTED_OR_OFF_TOPIC_USED_DB")

    for key, reason in (
        ("start_year_matches_expected", "START_YEAR_MISMATCH"),
        ("end_year_matches_expected", "END_YEAR_MISMATCH"),
        ("limit_matches_expected", "LIMIT_MISMATCH"),
    ):
        if rule_checks.get(key) is False:
            reasons.append(reason)
    if rule_checks.get("nam_false_positive"):
        reasons.append("NAM_FALSE_POSITIVE_FOR_VIETNAM")
    if judge_score is not None and judge_score < 50:
        reasons.append("JUDGE_SCORE_BELOW_50")
    return reasons


def sample_rows(response: dict[str, Any] | None, limit: int = 10) -> list[dict[str, Any]]:
    if not response:
        return []
    data = response.get("data")
    if isinstance(data, list) and data and isinstance(data[0], dict) and isinstance(data[0].get("rows"), list):
        return data[0]["rows"][:limit]
    chart_data = get_nested(response, ["chart", "data"])
    if isinstance(chart_data, list):
        return chart_data[:limit]
    return []


def chart_metadata(response: dict[str, Any] | None) -> dict[str, Any] | None:
    chart = response.get("chart") if response else None
    if not isinstance(chart, dict):
        return None
    return {key: value for key, value in chart.items() if key != "data"}


def build_judge_payload(
    case_id: str,
    turns: list[dict[str, Any]],
    target: dict[str, Any],
    rule_checks: dict[str, Any],
    rubric: str,
) -> dict[str, Any]:
    response = target.get("response") if isinstance(target.get("response"), dict) else {}
    return {
        "case_id": case_id,
        "category": target.get("category"),
        "description": target.get("description"),
        "turn_history": [
            {
                "turn_index": turn.get("turn_index"),
                "message": turn.get("message"),
                "ok": turn.get("ok"),
                "status": get_nested(turn, ["response", "status"]),
                "questionType": get_nested(turn, ["response", "questionType"]),
                "answer_preview": str(get_nested(turn, ["response", "answer"]) or "")[:300],
            }
            for turn in turns
        ],
        "target_user_message": target.get("message"),
        "expected": target.get("expected"),
        "final_answer": response.get("answer"),
        "final_response_metadata": {
            "status": response.get("status"),
            "questionType": response.get("questionType"),
            "toolsUsed": get_nested(response, ["metadata", "toolsUsed"]),
            "latency_ms": target.get("latency_ms"),
            "http_status": target.get("http_status"),
        },
        "parsedQuery": response.get("parsedQuery"),
        "routerDebug": response.get("routerDebug"),
        "parserDebug": response.get("parserDebug"),
        "chart": chart_metadata(response),
        "rows_sample": sample_rows(response),
        "clarificationQuestions": response.get("clarificationQuestions"),
        "warnings": response.get("warnings"),
        "rule_checks": rule_checks,
        "rubric": rubric,
    }


def build_prompt(payload: dict[str, Any]) -> str:
    return f"""
You are a strict evaluator for a Vietnamese government/economic data chat assistant.

Evaluate only the final user-visible answer and provided metadata. Do not answer the user question.
Return JSON only. Do not use markdown. Do not include extra prose.

Rules:
- If data rows are provided, judge whether the answer is grounded in those rows.
- Penalize internal system terms in user-visible final_answer.
- Penalize hallucinated numbers not present in rows/chart.
- For follow-up analysis, accept qualitative reasoning only if a caveat is present.
- For direct answer, parser/db should not be required.
- For unsupported/off-topic, reward graceful refusal and supported alternatives.
- If Vietnamese text is mojibake or unreadable, penalize clarity.

Return strict JSON:
{{
  "judge_status": "OK",
  "score": 0,
  "grade": "PASS|WARNING|FAIL",
  "category": "...",
  "criteria": {{
    "task_fulfillment": 0,
    "data_correctness_grounding": 0,
    "routing_tool_behavior": 0,
    "completeness_usefulness": 0,
    "clarity_vietnamese_ux": 0,
    "safety_scope_control": 0,
    "context_handling": 0,
    "formatting_ui_compatibility": 0
  }},
  "major_issues": [],
  "minor_issues": [],
  "hallucination_risk": "low|medium|high",
  "internal_terms_present": false,
  "grounding_notes": "...",
  "should_block_release": false,
  "recommendation": "..."
}}

Evaluation payload:
{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}
""".strip()


def strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return cleaned


class KeyManager:
    def __init__(self, api_keys: str) -> None:
        self.keys = [key.strip() for key in api_keys.split(",") if key.strip()]
        self.index = 0

    def has_keys(self) -> bool:
        return bool(self.keys)

    def next_key(self) -> tuple[int, str]:
        if not self.keys:
            raise ValueError("No Gemini API keys configured")
        key_index = self.index % len(self.keys)
        self.index += 1
        return key_index, self.keys[key_index]

    def count(self) -> int:
        return len(self.keys)


def gemini_generate(prompt: str, model: str, api_key: str, timeout_ms: int) -> tuple[int | None, str | None, str | None]:
    encoded_model = urllib.parse.quote(model, safe="")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{encoded_model}:generateContent?key={urllib.parse.quote(api_key)}"
    body = json.dumps(
        {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.0,
                "responseMimeType": "application/json",
            },
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_ms / 1000) as response:
            payload = json.loads(response.read().decode("utf-8"))
            text = get_nested(payload, ["candidates", 0, "content", "parts", 0, "text"])
            return response.status, str(text) if text is not None else None, None
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        return error.code, None, sanitize_error(raw or error.reason)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
        return None, None, sanitize_error(str(error))


def sanitize_error(error: str) -> str:
    return re.sub(r"key=[A-Za-z0-9_\-]+", "key=<redacted>", error)[:1000]


def parse_judge_json(text: str | None) -> dict[str, Any]:
    if not text:
        raise ValueError("empty Gemini judge response")
    parsed = json.loads(strip_code_fence(text))
    if not isinstance(parsed, dict):
        raise ValueError("judge response must be a JSON object")
    return normalize_judge(parsed)


def normalize_judge(judge: dict[str, Any]) -> dict[str, Any]:
    score = judge.get("score", 0)
    try:
        score_float = max(0.0, min(100.0, float(score)))
    except (TypeError, ValueError):
        score_float = 0.0
    judge["score"] = score_float
    grade = str(judge.get("grade") or "").upper()
    if grade not in {"PASS", "WARNING", "FAIL", "PASS_WITH_MINOR_ISSUES"}:
        if score_float >= 85:
            grade = "PASS"
        elif score_float >= 50:
            grade = "WARNING"
        else:
            grade = "FAIL"
    if grade == "PASS_WITH_MINOR_ISSUES":
        grade = "WARNING"
    judge["grade"] = grade
    judge["judge_status"] = str(judge.get("judge_status") or "OK")
    judge["should_block_release"] = bool(judge.get("should_block_release", False))
    if not isinstance(judge.get("criteria"), dict):
        judge["criteria"] = {}
    if not isinstance(judge.get("major_issues"), list):
        judge["major_issues"] = []
    if not isinstance(judge.get("minor_issues"), list):
        judge["minor_issues"] = []
    return judge


def judge_with_retries(
    prompt: str,
    key_manager: KeyManager,
    model: str,
    timeout_ms: int,
    max_retries: int,
    backoff_ms: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    last_error = "unknown judge error"
    for attempt in range(max_retries + 1):
        key_index, api_key = key_manager.next_key()
        print(f"Judge attempt {attempt + 1}/{max_retries + 1} key_index={key_index}", flush=True)
        http_status, text, error = gemini_generate(prompt, model, api_key, timeout_ms)
        attempts.append({"attempt": attempt + 1, "key_index": key_index, "http_status": http_status, "error": error})
        if error is None and http_status and 200 <= http_status < 300:
            try:
                return parse_judge_json(text), attempts
            except (json.JSONDecodeError, ValueError) as parse_error:
                last_error = sanitize_error(str(parse_error))
        else:
            last_error = error or f"HTTP {http_status}"

        retryable = http_status in RETRYABLE_HTTP or http_status is None or "json" in last_error.lower()
        if not retryable or attempt >= max_retries:
            break
        delay_ms = backoff_ms * (2**attempt) + random.randint(0, 250)
        time.sleep(delay_ms / 1000)

    return judge_error(last_error), attempts


def judge_error(error: str) -> dict[str, Any]:
    return {
        "judge_status": "JUDGE_ERROR",
        "score": 0.0,
        "grade": "FAIL",
        "category": None,
        "criteria": {},
        "major_issues": [sanitize_error(error)],
        "minor_issues": [],
        "hallucination_risk": "high",
        "internal_terms_present": False,
        "grounding_notes": "",
        "should_block_release": True,
        "recommendation": "Fix judge error and retry.",
    }


def no_valid_target_result(judge_run_id: str, case_id: str, turns: list[dict[str, Any]]) -> dict[str, Any]:
    first = turns[0] if turns else {}
    judge = judge_error("NO_VALID_TARGET_TURN")
    return {
        "run_id": first.get("run_id"),
        "judge_run_id": judge_run_id,
        "case_id": case_id,
        "category": first.get("category"),
        "description": first.get("description"),
        "conversation_id": first.get("conversation_id"),
        "target_turn_index": None,
        "target_message": None,
        "expected": {},
        "latency_ms": None,
        "rule_checks": compute_rule_checks(None),
        "hard_block_reasons": ["NO_VALID_TARGET_TURN"],
        "judge": judge,
        "final_score": 0.0,
        "grade": "FAIL",
        "should_block_release": True,
        "response_summary": {},
        "created_at": utc_now_iso(),
    }


def response_summary(target: dict[str, Any]) -> dict[str, Any]:
    response = target.get("response") if isinstance(target.get("response"), dict) else {}
    answer = str(response.get("answer") or "")
    return {
        "status": response.get("status"),
        "questionType": response.get("questionType"),
        "route": get_nested(response, ["routerDebug", "route"]),
        "intent": get_nested(response, ["parsedQuery", "intent"]),
        "parserSource": get_nested(response, ["parserDebug", "source"]),
        "answerPreview": answer[:300],
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def read_existing_judged(path: Path, retry_errors: bool) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    completed: dict[str, dict[str, Any]] = {}
    for record in read_jsonl(path):
        case_id = str(record.get("case_id", ""))
        judge_status = get_nested(record, ["judge", "judge_status"])
        if judge_status == "OK" or (judge_status == "JUDGE_ERROR" and not retry_errors):
            completed[case_id] = record
    return completed


def collect_issues(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        for issue in get_nested(record, ["judge", "major_issues"]) or []:
            text = str(issue)[:120]
            counts[text] = counts.get(text, 0) + 1
        for reason in record.get("hard_block_reasons") or []:
            counts[str(reason)] = counts.get(str(reason), 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True)[:20])


def summarize(judge_run_id_value: str, source_run_id: str | None, model: str, key_count: int, records: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [float(record.get("final_score", 0)) for record in records]
    by_category: dict[str, dict[str, Any]] = {}
    hallucination: dict[str, int] = {}
    internal_terms_cases: list[str] = []
    route_failures: list[str] = []
    slow_cases: list[dict[str, Any]] = []

    for record in records:
        category = str(record.get("category") or "UNKNOWN")
        score = float(record.get("final_score", 0))
        grade = str(record.get("grade") or "FAIL")
        bucket = by_category.setdefault(category, {"count": 0, "scores": [], "pass": 0, "warning": 0, "fail": 0, "blocked": 0})
        bucket["count"] += 1
        bucket["scores"].append(score)
        if grade == "PASS":
            bucket["pass"] += 1
        elif grade == "WARNING":
            bucket["warning"] += 1
        else:
            bucket["fail"] += 1
        if record.get("should_block_release"):
            bucket["blocked"] += 1
        risk = str(get_nested(record, ["judge", "hallucination_risk"]) or "unknown")
        hallucination[risk] = hallucination.get(risk, 0) + 1
        if record.get("rule_checks", {}).get("no_internal_terms") is False:
            internal_terms_cases.append(str(record.get("case_id")))
        if record.get("rule_checks", {}).get("route_matches_expected") is False:
            route_failures.append(str(record.get("case_id")))
        if isinstance(record.get("latency_ms"), int):
            slow_cases.append({"case_id": record.get("case_id"), "latency_ms": record.get("latency_ms")})

    for bucket in by_category.values():
        bucket["avg_score"] = round(sum(bucket["scores"]) / len(bucket["scores"]), 2) if bucket["scores"] else 0
        del bucket["scores"]

    return {
        "judge_run_id": judge_run_id_value,
        "source_run_id": source_run_id,
        "model": model,
        "gemini_key_count": key_count,
        "total_cases": len(records),
        "judged_cases": len(records),
        "pass": sum(1 for record in records if record.get("grade") == "PASS"),
        "warning": sum(1 for record in records if record.get("grade") == "WARNING"),
        "fail": sum(1 for record in records if record.get("grade") == "FAIL"),
        "blocked": sum(1 for record in records if record.get("should_block_release")),
        "avg_score": round(sum(scores) / len(scores), 2) if scores else 0,
        "median_score": round(statistics.median(scores), 2) if scores else 0,
        "by_category": by_category,
        "top_issues": collect_issues(records),
        "internal_terms_cases": internal_terms_cases,
        "hallucination_risk_counts": hallucination,
        "route_failures": route_failures,
        "slow_cases": sorted(slow_cases, key=lambda item: item["latency_ms"], reverse=True)[:10],
    }


def write_summary_md(path: Path, summary: dict[str, Any], records: list[dict[str, Any]]) -> None:
    lowest = sorted(records, key=lambda record: float(record.get("final_score", 0)))[:10]
    blocked = [record for record in records if record.get("should_block_release")]
    judge_errors = [record for record in records if get_nested(record, ["judge", "judge_status"]) == "JUDGE_ERROR"]
    lines = [
        "# Gemini Judge Summary",
        "",
        f"- Judge run ID: `{summary['judge_run_id']}`",
        f"- Source run ID: `{summary.get('source_run_id')}`",
        f"- Model: `{summary['model']}`",
        f"- Gemini keys configured: {summary['gemini_key_count']}",
        f"- Total cases: {summary['total_cases']}",
        f"- Avg score: {summary['avg_score']}",
        f"- Median score: {summary['median_score']}",
        f"- Pass: {summary['pass']}",
        f"- Warning: {summary['warning']}",
        f"- Fail: {summary['fail']}",
        f"- Blocked: {summary['blocked']}",
        "",
        "## Category Breakdown",
        "",
    ]
    for category, stats in sorted(summary["by_category"].items()):
        lines.append(
            f"- {category}: count={stats['count']}, avg={stats['avg_score']}, "
            f"pass={stats['pass']}, warning={stats['warning']}, fail={stats['fail']}, blocked={stats['blocked']}"
        )
    lines.extend(["", "## Blocked Cases", ""])
    lines.extend([f"- {record['case_id']}: {', '.join(record.get('hard_block_reasons') or [])}" for record in blocked] or ["- None"])
    lines.extend(["", "## Lowest Scores", ""])
    lines.extend([f"- {record['case_id']}: {record['final_score']} ({record['grade']})" for record in lowest] or ["- None"])
    lines.extend(["", "## Internal Term Cases", ""])
    lines.extend([f"- {case_id}" for case_id in summary["internal_terms_cases"]] or ["- None"])
    lines.extend(["", "## Judge Errors", ""])
    lines.extend([f"- {record['case_id']}: {get_nested(record, ['judge', 'major_issues'])}" for record in judge_errors] or ["- None"])
    lines.extend(["", "## Recommended Next Fixes", ""])
    if summary["top_issues"]:
        for issue, count in summary["top_issues"].items():
            lines.append(f"- {issue}: {count}")
    else:
        lines.append("- None")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def dry_run_summary(output_dir: Path, records: list[dict[str, Any]], selected: list[tuple[str, list[dict[str, Any]]]], rubric: str) -> dict[str, Any]:
    payloads = []
    for case_id, turns in selected:
        target = pick_target_turn(turns)
        rule_checks = compute_rule_checks(target)
        payloads.append(
            {
                "case_id": case_id,
                "target_turn_index": target.get("turn_index") if target else None,
                "rule_checks": rule_checks,
                "hard_block_reasons": hard_block_reasons(target, rule_checks),
                "prompt_payload_preview": build_judge_payload(case_id, turns, target, rule_checks, rubric) if target else None,
            }
        )
    summary = {
        "dry_run": True,
        "cases_loaded": len(records),
        "cases_selected": len(selected),
        "created_at": utc_now_iso(),
        "payloads": payloads,
    }
    write_json(output_dir / "dry_run_summary.json", summary)
    return summary


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()
    run_dir, raw_results_path, output_dir = resolve_paths(args)
    if raw_results_path is None or output_dir is None or not raw_results_path.exists():
        print("SKIPPED: no raw_results.jsonl found. Run Phase 9.1 collection first.")
        return 0
    output_dir.mkdir(parents=True, exist_ok=True)

    records = read_jsonl(raw_results_path)
    grouped = group_by_case(records)
    selected = select_cases(grouped, args.case_id, args.limit)
    source_run_id = records[0].get("run_id") if records else (run_dir.name if run_dir else None)
    rubric = Path(args.rubric).read_text(encoding="utf-8") if Path(args.rubric).exists() else ""

    if args.dry_run:
        summary = dry_run_summary(output_dir, records, selected, rubric)
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
        return 0

    key_manager = KeyManager(args.api_keys)
    if not key_manager.has_keys():
        print("SKIPPED: no Gemini API keys configured. Set EVAL_GEMINI_API_KEYS or GEMINI_API_KEY.")
        return 0

    if args.concurrency != 1:
        print("Concurrency > 1 requested, but sequential judging is used to avoid Gemini preview overload.")

    judged_path = output_dir / "judged_results.jsonl"
    if args.overwrite and judged_path.exists():
        judged_path.unlink()
    completed = read_existing_judged(judged_path, args.retry_errors) if args.resume else {}
    all_results = list(completed.values())
    current_judge_run_id = judge_run_id()

    for case_id, turns in selected:
        if case_id in completed:
            continue
        target = pick_target_turn(turns)
        if target is None:
            result = no_valid_target_result(current_judge_run_id, case_id, turns)
        else:
            rule_checks = compute_rule_checks(target)
            prompt_payload = build_judge_payload(case_id, turns, target, rule_checks, rubric)
            prompt = build_prompt(prompt_payload)
            judge, attempts = judge_with_retries(
                prompt,
                key_manager,
                args.model,
                args.timeout_ms,
                args.max_retries,
                args.retry_backoff_ms,
            )
            initial_blocks = hard_block_reasons(target, rule_checks)
            final_blocks = hard_block_reasons(target, rule_checks, float(judge.get("score", 0)))
            hard_blocks = sorted(set(initial_blocks + final_blocks))
            if hard_blocks:
                judge["should_block_release"] = True
            final_score = float(judge.get("score", 0))
            grade = str(judge.get("grade") or ("PASS" if final_score >= 85 else "WARNING" if final_score >= 50 else "FAIL"))
            if hard_blocks and final_score < 50:
                grade = "FAIL"
            result = {
                "run_id": target.get("run_id"),
                "judge_run_id": current_judge_run_id,
                "case_id": case_id,
                "category": target.get("category"),
                "description": target.get("description"),
                "conversation_id": target.get("conversation_id"),
                "target_turn_index": target.get("turn_index"),
                "target_message": target.get("message"),
                "expected": target.get("expected"),
                "latency_ms": target.get("latency_ms"),
                "rule_checks": rule_checks,
                "hard_block_reasons": hard_blocks,
                "judge_attempts": attempts,
                "judge": judge,
                "final_score": final_score,
                "grade": grade if grade in {"PASS", "WARNING", "FAIL"} else "WARNING",
                "should_block_release": bool(judge.get("should_block_release") or hard_blocks),
                "response_summary": response_summary(target),
                "created_at": utc_now_iso(),
            }
        append_jsonl(judged_path, result)
        if result["should_block_release"]:
            append_jsonl(output_dir / "judge_errors.jsonl", result)
        all_results.append(result)
        if args.fail_fast and get_nested(result, ["judge", "judge_status"]) == "JUDGE_ERROR":
            break
        if args.sleep_ms > 0:
            time.sleep(args.sleep_ms / 1000)

    write_json(output_dir / "judged_results.pretty.json", all_results)
    summary = summarize(current_judge_run_id, str(source_run_id) if source_run_id else None, args.model, key_manager.count(), all_results)
    write_json(output_dir / "judge_summary.json", summary)
    write_summary_md(output_dir / "judge_summary.md", summary, all_results)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
