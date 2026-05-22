from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import os
import random
import re
import statistics
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_MODEL = "gemini-3.1-flash-lite-preview"
SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
RESULT_ROOT = PIPELINE_ROOT / "result"
ENV_PATH = SCRIPT_DIR / ".env"
DEFAULT_RUN_ROOT = RESULT_ROOT
OUTPUT_FILE_NAME = "judge_results.json"

INTERNAL_TERMS = [
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
]

RETRYABLE_HTTP = {429, 500, 502, 503, 504}


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

        if not key:
            continue

        if (
            (value.startswith('"') and value.endswith('"'))
            or (value.startswith("'") and value.endswith("'"))
        ):
            value = value[1:-1]

        if key not in os.environ:
            os.environ[key] = value


def load_env_files() -> None:
    load_env_file(ENV_PATH)
    if ENV_PATH.exists():
        print(f"Loaded env file: {ENV_PATH}")


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def make_judge_run_id() -> str:
    return "judge_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simple Gemini judge for collected chat responses.")

    parser.add_argument(
        "--run-dir",
        default=os.getenv("EVAL_RUN_DIR"),
        help="Run directory containing raw_results.jsonl. Default: latest evalFullPipeline/result/<run_id>.",
    )
    parser.add_argument(
        "--raw-results",
        default=os.getenv("EVAL_RAW_RESULTS"),
        help="Path to raw_results.jsonl. Overrides --run-dir.",
    )
    parser.add_argument(
        "--output",
        default=os.getenv("EVAL_JUDGE_OUTPUT"),
        help="Output JSON path. Default: <run-dir>/judge_results.json.",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("EVAL_GEMINI_MODEL", DEFAULT_MODEL),
    )
    parser.add_argument(
        "--api-keys",
        default=os.getenv("EVAL_GEMINI_API_KEYS") or os.getenv("GEMINI_API_KEY") or "",
        help="Comma-separated Gemini API keys.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=int(os.getenv("EVAL_JUDGE_WORKERS", "5")),
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=int(os.getenv("EVAL_JUDGE_MAX_RETRIES", "10")),
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=int(os.getenv("EVAL_JUDGE_TIMEOUT_MS", "30000")),
    )
    parser.add_argument(
        "--retry-backoff-ms",
        type=int,
        default=int(os.getenv("EVAL_JUDGE_RETRY_BACKOFF_MS", "1500")),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Judge first N cases only.",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        help="Judge only specific case_id. Can be passed multiple times.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Ignore existing judge_results.json.",
    )
    parser.add_argument("--resume", action="store_true", help="Keep existing successful results in judge_results.json.")
    parser.add_argument("--dry-run", action="store_true", help="Build results with rule checks only; do not call Gemini.")

    return parser.parse_args()


def latest_run_dir() -> Path | None:
    if not DEFAULT_RUN_ROOT.exists():
        return None

    candidates = [
        path
        for path in DEFAULT_RUN_ROOT.iterdir()
        if path.is_dir() and (path / "raw_results.jsonl").exists()
    ]

    if not candidates:
        return None

    return sorted(candidates)[-1]


def resolve_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    if args.raw_results:
        raw_path = Path(args.raw_results)
        run_dir = raw_path.parent
    elif args.run_dir:
        run_dir = Path(args.run_dir)
        raw_path = run_dir / "raw_results.jsonl"
    else:
        run_dir = latest_run_dir()
        if run_dir is None:
            raise FileNotFoundError(f"No run directory found under {DEFAULT_RUN_ROOT}.")
        raw_path = run_dir / "raw_results.jsonl"

    if not raw_path.exists():
        raise FileNotFoundError(f"raw_results.jsonl not found: {raw_path}")

    output_path = Path(args.output) if args.output else run_dir / OUTPUT_FILE_NAME
    return raw_path, output_path


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                item = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {e}") from e

            if isinstance(item, dict):
                records.append(item)

    return records


def group_by_case(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}

    for record in records:
        case_id = str(record.get("case_id") or "")
        if not case_id:
            continue
        grouped.setdefault(case_id, []).append(record)

    for turns in grouped.values():
        turns.sort(key=lambda x: int(x.get("turn_index", 0)))

    return grouped


def select_cases(
    grouped: dict[str, list[dict[str, Any]]],
    case_ids: list[str],
    limit: int | None,
) -> list[tuple[str, list[dict[str, Any]]]]:
    items = sorted(grouped.items(), key=lambda x: x[0])

    if case_ids:
        wanted = set(case_ids)
        items = [(case_id, turns) for case_id, turns in items if case_id in wanted]

    if limit is not None:
        items = items[: max(limit, 0)]

    return items


def pick_target_turn(turns: list[dict[str, Any]]) -> dict[str, Any] | None:
    flagged = [t for t in turns if t.get("is_judge_target_turn")]
    if flagged:
        return flagged[-1]

    not_skipped = [t for t in turns if not t.get("skipped")]
    if not_skipped:
        return not_skipped[-1]

    return turns[-1] if turns else None


def get_nested(value: Any, keys: list[Any]) -> Any:
    current = value

    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list) and isinstance(key, int):
            if 0 <= key < len(current):
                current = current[key]
            else:
                return None
        else:
            return None

    return current


def has_internal_terms(answer: str | None) -> bool:
    if not answer:
        return False

    lower = answer.lower()
    return any(term.lower() in lower for term in INTERNAL_TERMS)


def get_rows(response: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
    data = response.get("data")

    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict) and isinstance(first.get("rows"), list):
            return first["rows"][:limit]

    chart_data = get_nested(response, ["chart", "data"])
    if isinstance(chart_data, list):
        return chart_data[:limit]

    return []


def get_chart_meta(response: dict[str, Any]) -> dict[str, Any] | None:
    chart = response.get("chart")
    if not isinstance(chart, dict):
        return None

    return {
        key: value
        for key, value in chart.items()
        if key != "data"
    }


def value_matches(actual: Any, expected: Any) -> bool | None:
    if expected is None:
        return None
    if isinstance(expected, list):
        return actual in expected
    return actual == expected


def compute_rule_checks(target: dict[str, Any]) -> dict[str, Any]:
    response = target.get("response") if isinstance(target.get("response"), dict) else {}
    expected = target.get("expected") if isinstance(target.get("expected"), dict) else {}
    answer = response.get("answer")
    parsed_query = response.get("parsedQuery") if isinstance(response.get("parsedQuery"), dict) else {}
    router_debug = response.get("routerDebug") if isinstance(response.get("routerDebug"), dict) else {}

    target_message = str(target.get("message") or "")
    parsed_countries = parsed_query.get("countries")
    metadata_countries = get_nested(response, ["metadata", "countries"])

    all_countries: list[str] = []
    if isinstance(parsed_countries, list):
        all_countries.extend(str(x).upper() for x in parsed_countries)
    if isinstance(metadata_countries, list):
        all_countries.extend(str(x).upper() for x in metadata_countries)

    vi_nam_mentioned = "việt nam" in target_message.lower() or "viet nam" in target_message.lower()
    nam_false_positive = vi_nam_mentioned and "NAM" in set(all_countries)

    rows = get_rows(response)

    return {
        "has_answer": isinstance(answer, str) and bool(answer.strip()),
        "no_internal_terms": not has_internal_terms(answer if isinstance(answer, str) else None),
        "status_matches_expected": value_matches(response.get("status"), expected.get("status")),
        "question_type_matches_expected": value_matches(response.get("questionType"), expected.get("questionType")),
        "route_matches_expected": value_matches(router_debug.get("route"), expected.get("route")),
        "intent_matches_expected": value_matches(parsed_query.get("intent"), expected.get("intent")),
        "start_year_matches_expected": value_matches(parsed_query.get("start_year"), expected.get("start_year")),
        "end_year_matches_expected": value_matches(parsed_query.get("end_year"), expected.get("end_year")),
        "limit_matches_expected": value_matches(parsed_query.get("limit"), expected.get("limit")),
        "has_chart": isinstance(response.get("chart"), dict) and response["chart"].get("type") not in (None, "none"),
        "has_rows": bool(rows),
        "nam_false_positive": nam_false_positive,
        "latency_ms": target.get("latency_ms"),
    }


def hard_block_reasons(target: dict[str, Any], rule_checks: dict[str, Any], judge_score: float | None = None) -> list[str]:
    response = target.get("response") if isinstance(target.get("response"), dict) else {}
    expected = target.get("expected") if isinstance(target.get("expected"), dict) else {}
    category = str(target.get("category") or "")

    reasons: list[str] = []

    if not target.get("ok"):
        reasons.append("TARGET_TURN_NOT_OK")

    if not rule_checks.get("has_answer"):
        reasons.append("EMPTY_ANSWER")

    if not rule_checks.get("no_internal_terms"):
        reasons.append("INTERNAL_TERMS_IN_ANSWER")

    if rule_checks.get("nam_false_positive"):
        reasons.append("NAM_FALSE_POSITIVE_FOR_VIETNAM")

    expected_status = expected.get("status")
    actual_status = response.get("status")

    if expected_status == "success" and actual_status in {"needs_clarification", "unsupported", "off_topic", "error"}:
        reasons.append("EXPECTED_SUCCESS_BUT_STOPPED")

    if category == "FOLLOW_UP_ANALYSIS":
        parser_debug = response.get("parserDebug")
        needs_parser = get_nested(response, ["routerDebug", "needs_parser"])
        needs_db = get_nested(response, ["routerDebug", "needs_db"])
        if parser_debug is not None or needs_parser is True or needs_db is True:
            reasons.append("FOLLOW_UP_ANALYSIS_USED_PARSER_OR_DB")

    if category == "FOLLOW_UP_MODIFY_QUERY":
        route = get_nested(response, ["routerDebug", "route"])
        if route != "FOLLOW_UP_MODIFY_QUERY":
            reasons.append("FOLLOW_UP_MODIFY_ROUTE_MISMATCH")

    if category == "NEED_CLARIFICATION":
        questions = response.get("clarificationQuestions")
        answer = str(response.get("answer") or "")
        has_question = isinstance(questions, list) and len(questions) > 0
        has_question = has_question or "?" in answer
        if not has_question:
            reasons.append("NEED_CLARIFICATION_WITHOUT_QUESTION")

    if category == "UNSUPPORTED_OFF_TOPIC":
        needs_db = get_nested(response, ["routerDebug", "needs_db"])
        if actual_status == "success" and needs_db is True:
            reasons.append("UNSUPPORTED_OR_OFF_TOPIC_USED_DB")

    for key, reason in [
        ("start_year_matches_expected", "START_YEAR_MISMATCH"),
        ("end_year_matches_expected", "END_YEAR_MISMATCH"),
        ("limit_matches_expected", "LIMIT_MISMATCH"),
    ]:
        if rule_checks.get(key) is False:
            reasons.append(reason)

    if judge_score is not None and judge_score < 50:
        reasons.append("JUDGE_SCORE_BELOW_50")

    return sorted(set(reasons))


def build_prompt(case_id: str, turns: list[dict[str, Any]], target: dict[str, Any], rule_checks: dict[str, Any]) -> str:
    response = target.get("response") if isinstance(target.get("response"), dict) else {}

    payload = {
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
        "final_status": response.get("status"),
        "final_question_type": response.get("questionType"),
        "parsedQuery": response.get("parsedQuery"),
        "routerDebug": response.get("routerDebug"),
        "parserDebug": response.get("parserDebug"),
        "chart": get_chart_meta(response),
        "rows_sample": get_rows(response),
        "clarificationQuestions": response.get("clarificationQuestions"),
        "warnings": response.get("warnings"),
        "metadata_tools_used": get_nested(response, ["metadata", "toolsUsed"]),
        "rule_checks": rule_checks,
    }

    rubric = """
Score the final answer from 0 to 100.

General criteria:
1. Task fulfillment
2. Data correctness / grounding
3. Routing and tool behavior
4. Completeness and usefulness
5. Vietnamese clarity and user-facing tone
6. Safety and scope control
7. Conversation context handling
8. Formatting and UI compatibility

Category-specific expectations:
- DIRECT_ANSWER: answer should be simple, correct, user-facing, no parser/db needed.
- DATA_QUERY_*: answer must match rows/chart/metadata, not hallucinate numbers.
- FOLLOW_UP_ANALYSIS: must use previous context, must not call parser/db, should include qualitative caveat when explaining causes.
- FOLLOW_UP_MODIFY_QUERY: must rewrite/use previous query context correctly, expected slots must match.
- NEED_CLARIFICATION: must ask the right missing information clearly.
- UNSUPPORTED_OFF_TOPIC: must refuse or redirect gracefully and avoid DB/tool use.

Hard penalties:
- Internal system terms in user answer.
- Hallucinated numbers not in rows/chart.
- Wrong route/status for the case.
- Empty answer.
- Follow-up analysis using parser/db.
- Vietnam resolved as NAM.
""".strip()

    return f"""
You are a strict evaluator for a Vietnamese government/economic data chat assistant.

Do not answer the user's question.
Only evaluate the final assistant answer and metadata.
Return JSON only. No markdown. No extra text.

Return this exact JSON shape:
{{
  "score": 0,
  "grade": "PASS|WARNING|FAIL",
  "major_issues": [],
  "minor_issues": [],
  "hallucination_risk": "low|medium|high",
  "internal_terms_present": false,
  "grounding_notes": "",
  "should_block_release": false,
  "recommendation": ""
}}

Grade guide:
- PASS: score >= 85
- WARNING: 50 <= score < 85
- FAIL: score < 50

Rubric:
{rubric}

Evaluation payload:
{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}
""".strip()


def strip_code_fence(text: str) -> str:
    cleaned = text.strip()

    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    return cleaned


def sanitize_error(error: str) -> str:
    error = re.sub(r"key=[A-Za-z0-9_\-]+", "key=<redacted>", error)
    return error[:1000]


def normalize_judge(judge: dict[str, Any]) -> dict[str, Any]:
    try:
        score = float(judge.get("score", 0))
    except (TypeError, ValueError):
        score = 0.0

    score = max(0.0, min(100.0, score))

    grade = str(judge.get("grade") or "").upper()
    if grade not in {"PASS", "WARNING", "FAIL"}:
        if score >= 85:
            grade = "PASS"
        elif score >= 50:
            grade = "WARNING"
        else:
            grade = "FAIL"

    return {
        "judge_status": str(judge.get("judge_status") or "OK"),
        "score": score,
        "grade": grade,
        "major_issues": judge.get("major_issues") if isinstance(judge.get("major_issues"), list) else [],
        "minor_issues": judge.get("minor_issues") if isinstance(judge.get("minor_issues"), list) else [],
        "hallucination_risk": str(judge.get("hallucination_risk") or "unknown"),
        "internal_terms_present": bool(judge.get("internal_terms_present", False)),
        "grounding_notes": str(judge.get("grounding_notes") or ""),
        "should_block_release": bool(judge.get("should_block_release", False)),
        "recommendation": str(judge.get("recommendation") or ""),
    }


def parse_judge_response(text: str) -> dict[str, Any]:
    parsed = json.loads(strip_code_fence(text))

    if not isinstance(parsed, dict):
        raise ValueError("Judge response is not a JSON object.")

    return normalize_judge(parsed)


def gemini_generate(prompt: str, model: str, api_key: str, timeout_ms: int) -> tuple[int | None, str | None, str | None]:
    model_encoded = urllib.parse.quote(model, safe="")
    key_encoded = urllib.parse.quote(api_key, safe="")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_encoded}:generateContent?key={key_encoded}"

    body = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": 0.0,
            "responseMimeType": "application/json",
        },
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_ms / 1000) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            text = get_nested(payload, ["candidates", 0, "content", "parts", 0, "text"])
            return resp.status, str(text) if text is not None else None, None

    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        return e.code, None, sanitize_error(raw or str(e))

    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        return None, None, sanitize_error(str(e))


class KeyPool:
    def __init__(self, raw_keys: str) -> None:
        cleaned: list[str] = []

        raw_keys = raw_keys.strip()

        if raw_keys.startswith("EVAL_GEMINI_API_KEYS="):
            raw_keys = raw_keys.split("=", 1)[1].strip()

        for item in raw_keys.split(","):
            key = item.strip()

            if (
                (key.startswith('"') and key.endswith('"'))
                or (key.startswith("'") and key.endswith("'"))
            ):
                key = key[1:-1].strip()

            if key:
                cleaned.append(key)

        self.keys = cleaned
        self.lock = threading.Lock()
        self.index = 0

    def count(self) -> int:
        return len(self.keys)

    def next_key(self) -> tuple[int, str]:
        if not self.keys:
            raise RuntimeError("No Gemini API keys configured.")

        with self.lock:
            idx = self.index % len(self.keys)
            self.index += 1

        return idx, self.keys[idx]


def judge_error(message: str) -> dict[str, Any]:
    return {
        "judge_status": "JUDGE_ERROR",
        "score": 0.0,
        "grade": "FAIL",
        "major_issues": [sanitize_error(message)],
        "minor_issues": [],
        "hallucination_risk": "high",
        "internal_terms_present": False,
        "grounding_notes": "",
        "should_block_release": True,
        "recommendation": "Fix judge/API error and retry.",
    }


def judge_with_retry(
    prompt: str,
    model: str,
    key_pool: KeyPool,
    max_retries: int,
    timeout_ms: int,
    backoff_ms: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    last_error = "unknown error"

    for attempt in range(1, max_retries + 1):
        key_index, key = key_pool.next_key()

        http_status, text, error = gemini_generate(prompt, model, key, timeout_ms)

        attempts.append(
            {
                "attempt": attempt,
                "key_index": key_index,
                "http_status": http_status,
                "error": error,
            }
        )

        if error is None and http_status is not None and 200 <= http_status < 300 and text:
            try:
                return parse_judge_response(text), attempts
            except Exception as e:
                last_error = f"Invalid JSON from Gemini judge: {e}"
        else:
            last_error = error or f"HTTP {http_status}"

        retryable = (
            http_status in RETRYABLE_HTTP
            or http_status is None
            or http_status == 400
            or "json" in str(last_error).lower()
            or "api_key_invalid" in str(last_error).lower()
            or "api key not valid" in str(last_error).lower()
        )

        if not retryable:
            break

        delay = (backoff_ms * (2 ** min(attempt - 1, 4))) + random.randint(0, 300)
        time.sleep(delay / 1000)

    return judge_error(last_error), attempts


def make_result(
    judge_run_id: str,
    case_id: str,
    turns: list[dict[str, Any]],
    target: dict[str, Any],
    judge: dict[str, Any],
    judge_attempts: list[dict[str, Any]],
    rule_checks: dict[str, Any],
) -> dict[str, Any]:
    response = target.get("response") if isinstance(target.get("response"), dict) else {}
    answer = str(response.get("answer") or "")

    score = float(judge.get("score", 0))
    blocks = hard_block_reasons(target, rule_checks, score)

    should_block = bool(blocks) or bool(judge.get("should_block_release"))
    grade = str(judge.get("grade") or "FAIL")

    if should_block and score < 50:
        grade = "FAIL"

    return {
        "case_id": case_id,
        "category": target.get("category"),
        "description": target.get("description"),
        "conversation_id": target.get("conversation_id"),
        "target_turn_index": target.get("turn_index"),
        "target_message": target.get("message"),
        "expected": target.get("expected"),
        "latency_ms": target.get("latency_ms"),
        "rule_checks": rule_checks,
        "hard_block_reasons": blocks,
        "judge_attempts": judge_attempts,
        "judge": judge,
        "final_score": score,
        "grade": grade,
        "should_block_release": should_block,
        "response_summary": {
            "status": response.get("status"),
            "questionType": response.get("questionType"),
            "route": get_nested(response, ["routerDebug", "route"]),
            "intent": get_nested(response, ["parsedQuery", "intent"]),
            "parserSource": get_nested(response, ["parserDebug", "source"]),
            "answerPreview": answer[:300],
        },
        "created_at": now_iso(),
        "turn_count": len(turns),
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [float(r.get("final_score", 0)) for r in results]

    by_category: dict[str, dict[str, Any]] = {}
    top_issues: dict[str, int] = {}
    hallucination_risk_counts: dict[str, int] = {}

    for r in results:
        category = str(r.get("category") or "UNKNOWN")
        grade = str(r.get("grade") or "FAIL")
        score = float(r.get("final_score", 0))

        bucket = by_category.setdefault(
            category,
            {
                "count": 0,
                "pass": 0,
                "warning": 0,
                "fail": 0,
                "blocked": 0,
                "scores": [],
            },
        )

        bucket["count"] += 1
        bucket["scores"].append(score)

        if grade == "PASS":
            bucket["pass"] += 1
        elif grade == "WARNING":
            bucket["warning"] += 1
        else:
            bucket["fail"] += 1

        if r.get("should_block_release"):
            bucket["blocked"] += 1

        risk = str(get_nested(r, ["judge", "hallucination_risk"]) or "unknown")
        hallucination_risk_counts[risk] = hallucination_risk_counts.get(risk, 0) + 1

        for issue in r.get("hard_block_reasons") or []:
            top_issues[issue] = top_issues.get(issue, 0) + 1

        for issue in get_nested(r, ["judge", "major_issues"]) or []:
            text = str(issue)[:160]
            top_issues[text] = top_issues.get(text, 0) + 1

    for bucket in by_category.values():
        bucket["avg_score"] = round(sum(bucket["scores"]) / len(bucket["scores"]), 2) if bucket["scores"] else 0
        del bucket["scores"]

    return {
        "total_cases": len(results),
        "pass": sum(1 for r in results if r.get("grade") == "PASS"),
        "warning": sum(1 for r in results if r.get("grade") == "WARNING"),
        "fail": sum(1 for r in results if r.get("grade") == "FAIL"),
        "blocked": sum(1 for r in results if r.get("should_block_release")),
        "avg_score": round(sum(scores) / len(scores), 2) if scores else 0,
        "median_score": round(statistics.median(scores), 2) if scores else 0,
        "by_category": by_category,
        "top_issues": dict(sorted(top_issues.items(), key=lambda x: x[1], reverse=True)[:30]),
        "internal_terms_cases": [
            r.get("case_id")
            for r in results
            if r.get("rule_checks", {}).get("no_internal_terms") is False
        ],
        "route_failures": [
            r.get("case_id")
            for r in results
            if r.get("rule_checks", {}).get("route_matches_expected") is False
        ],
        "hallucination_risk_counts": hallucination_risk_counts,
        "slow_cases": sorted(
            [
                {
                    "case_id": r.get("case_id"),
                    "category": r.get("category"),
                    "latency_ms": r.get("latency_ms"),
                }
                for r in results
                if isinstance(r.get("latency_ms"), int)
            ],
            key=lambda x: x["latency_ms"],
            reverse=True,
        )[:10],
    }


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")

    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )

    tmp_path.replace(path)


def main() -> int:
    load_env_files()
    args = parse_args()

    raw_path, output_path = resolve_paths(args)

    records = read_jsonl(raw_path)
    grouped = group_by_case(records)
    selected = select_cases(grouped, args.case_id, args.limit)

    if not selected:
        print("No cases selected.")
        return 1

    key_pool = KeyPool(args.api_keys)

    if args.overwrite or not output_path.exists():
        existing_results: list[dict[str, Any]] = []
    else:
        try:
            existing_payload = json.loads(output_path.read_text(encoding="utf-8"))
            existing_results = existing_payload.get("results") if isinstance(existing_payload.get("results"), list) else []
        except Exception:
            existing_results = []

    existing_by_case = {str(r.get("case_id")): r for r in existing_results if r.get("case_id")}
    judge_run_id = make_judge_run_id()

    print(f"Raw results: {raw_path}")
    print(f"Output: {output_path}")
    print(f"Cases selected: {len(selected)}")
    print(f"Gemini keys configured: {key_pool.count()}")
    print(f"Workers: {min(args.workers, len(selected), max(key_pool.count(), 1))}")
    print(f"Max retries per case: {args.max_retries}")

    work_items: list[tuple[str, list[dict[str, Any]]]] = []
    results: list[dict[str, Any]] = []

    for case_id, turns in selected:
        if case_id in existing_by_case and not args.overwrite:
            results.append(existing_by_case[case_id])
        else:
            work_items.append((case_id, turns))

    if args.dry_run:
        for case_id, turns in work_items:
            target = pick_target_turn(turns)
            if target is None:
                continue
            rule_checks = compute_rule_checks(target)
            judge = {
                "judge_status": "DRY_RUN",
                "score": 0.0,
                "grade": "WARNING",
                "major_issues": [],
                "minor_issues": [],
                "hallucination_risk": "unknown",
                "internal_terms_present": not rule_checks.get("no_internal_terms", True),
                "grounding_notes": "",
                "should_block_release": False,
                "recommendation": "",
            }
            results.append(make_result(judge_run_id, case_id, turns, target, judge, [], rule_checks))
        final_results = sorted(results, key=lambda r: str(r.get("case_id") or ""))
        final_payload = {
            "metadata": {
                "judge_run_id": judge_run_id,
                "source_run_id": records[0].get("run_id") if records else None,
                "run_dir": str(output_path.parent),
                "raw_results_path": str(raw_path),
                "output_file": str(output_path),
                "model": args.model,
                "gemini_key_count": key_pool.count(),
                "workers": 0,
                "max_retries": args.max_retries,
                "mode": "dry_run",
                "created_at": now_iso(),
            },
            "summary": summarize(final_results),
            "results": final_results,
        }
        atomic_write_json(output_path, final_payload)
        print(json.dumps(final_payload["summary"], ensure_ascii=False, indent=2, default=str))
        print(f"Result file: {output_path}")
        return 0

    if key_pool.count() == 0:
        print("No Gemini API keys found.")
        print(f"Put EVAL_GEMINI_API_KEYS in {ENV_PATH}")
        return 1

    lock = threading.Lock()

    def run_one(item: tuple[str, list[dict[str, Any]]]) -> dict[str, Any]:
        case_id, turns = item
        target = pick_target_turn(turns)

        if target is None:
            fake_target = {
                "category": turns[0].get("category") if turns else None,
                "description": turns[0].get("description") if turns else None,
                "message": None,
                "expected": {},
                "ok": False,
                "response": {"answer": ""},
                "latency_ms": None,
            }
            rule_checks = compute_rule_checks(fake_target)
            judge = judge_error("No target turn found.")
            return make_result(judge_run_id, case_id, turns, fake_target, judge, [], rule_checks)

        rule_checks = compute_rule_checks(target)
        prompt = build_prompt(case_id, turns, target, rule_checks)

        judge, attempts = judge_with_retry(
            prompt=prompt,
            model=args.model,
            key_pool=key_pool,
            max_retries=args.max_retries,
            timeout_ms=args.timeout_ms,
            backoff_ms=args.retry_backoff_ms,
        )

        return make_result(judge_run_id, case_id, turns, target, judge, attempts, rule_checks)

    max_workers = max(1, min(args.workers, len(work_items), key_pool.count()))

    if work_items:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(run_one, item): item[0] for item in work_items}

            for future in concurrent.futures.as_completed(future_map):
                case_id = future_map[future]

                try:
                    result = future.result()
                except Exception as e:
                    result = {
                        "case_id": case_id,
                        "category": None,
                        "description": None,
                        "target_message": None,
                        "rule_checks": {},
                        "hard_block_reasons": ["SCRIPT_EXCEPTION"],
                        "judge_attempts": [],
                        "judge": judge_error(str(e)),
                        "final_score": 0.0,
                        "grade": "FAIL",
                        "should_block_release": True,
                        "response_summary": {},
                        "created_at": now_iso(),
                    }

                with lock:
                    results = list(existing_by_case.values())
                    existing_by_case[case_id] = result
                    results = list(existing_by_case.values())

                    summary = summarize(results)
                    payload = {
                        "metadata": {
                            "judge_run_id": judge_run_id,
                            "source_run_id": records[0].get("run_id") if records else None,
                            "run_dir": str(output_path.parent),
                            "raw_results_path": str(raw_path),
                            "output_file": str(output_path),
                            "model": args.model,
                            "gemini_key_count": key_pool.count(),
                            "workers": max_workers,
                            "max_retries": args.max_retries,
                            "mode": "judge",
                            "created_at": now_iso(),
                        },
                        "summary": summary,
                        "results": sorted(results, key=lambda r: str(r.get("case_id") or "")),
                    }

                    atomic_write_json(output_path, payload)

                print(
                    f"[{len(existing_by_case)}/{len(selected)}] {case_id} "
                    f"score={result.get('final_score')} grade={result.get('grade')} "
                    f"blocked={result.get('should_block_release')}",
                    flush=True,
                )

    final_results = sorted(existing_by_case.values(), key=lambda r: str(r.get("case_id") or ""))
    final_summary = summarize(final_results)

    final_payload = {
        "metadata": {
            "judge_run_id": judge_run_id,
            "source_run_id": records[0].get("run_id") if records else None,
            "run_dir": str(output_path.parent),
            "raw_results_path": str(raw_path),
            "output_file": str(output_path),
            "model": args.model,
            "gemini_key_count": key_pool.count(),
            "workers": max_workers,
            "max_retries": args.max_retries,
            "mode": "judge",
            "created_at": now_iso(),
        },
        "summary": final_summary,
        "results": final_results,
    }

    atomic_write_json(output_path, final_payload)

    print("")
    print("DONE")
    print(json.dumps(final_summary, ensure_ascii=False, indent=2, default=str))
    print("")
    print(f"Result file: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
