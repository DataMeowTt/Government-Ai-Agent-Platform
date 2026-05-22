import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any

from app.core.config import settings
from app.llm.gemini_client import GeminiClientError, generate_gemini_text, is_gemini_enabled
from app.router.front_router_prompt import ALLOWED_FRONT_ROUTES, build_front_router_prompt


logger = logging.getLogger(__name__)


def route_with_front_llm_draft(
    user_message: str,
    conversation_context: dict[str, Any],
    rule_route_draft: Any | None = None,
) -> dict[str, Any] | None:
    if not settings.enable_front_llm_router:
        return None

    if not is_gemini_enabled():
        return None

    prompt = build_front_router_prompt(
        user_message=user_message,
        conversation_context=conversation_context,
        rule_route_draft=rule_route_draft,
    )

    try:
        text = _generate_with_timeout(prompt)
        parsed = _parse_json_object(text)
        return _sanitize_front_router_result(parsed)
    except (GeminiClientError, json.JSONDecodeError, ValueError, TimeoutError) as error:
        logger.warning("Front LLM router failed: %s", error)
        return None
    except Exception:
        logger.exception("Unexpected Front LLM router error")
        return None


def _generate_with_timeout(prompt: str) -> str:
    timeout_seconds = max(settings.gemini_router_timeout_ms, 1) / 1000

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(
        generate_gemini_text,
        prompt,
        settings.gemini_router_model,
    )

    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeoutError as error:
        raise TimeoutError("Front LLM router timeout") from error
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _parse_json_object(text: str) -> dict[str, Any]:
    cleaned = _strip_code_fence(text)
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("Front router response must be a JSON object")
    return data


def _sanitize_front_router_result(data: dict[str, Any]) -> dict[str, Any]:
    route = str(data.get("route") or "").upper().strip()
    if route in {"DIRECT_ANSWER"}:
        route = "GENERAL_EXPLANATION"
    if route in {"FOLLOW_UP_MODIFY_QUERY", "FOLLOW_UP_MODIFY"}:
        route = "DATA_QUERY"
    if route not in ALLOWED_FRONT_ROUTES:
        route = "DATA_QUERY"

    result = {
        "route": route,
        "answer": _optional_str(data.get("answer")),
        "rewritten_query": _optional_str(data.get("rewritten_query")),
        "needs_parser": bool(data.get("needs_parser")),
        "needs_db": bool(data.get("needs_db")),
        "clarification_question": _optional_str(data.get("clarification_question")),
        "uses_previous_context": bool(data.get("uses_previous_context")),
        "confidence": _clamp_float(data.get("confidence"), 0.0, 1.0),
        "reason": _optional_str(data.get("reason")) or "",
    }

    if route == "GENERAL_EXPLANATION":
        result["needs_parser"] = False
        result["needs_db"] = False
        result["rewritten_query"] = None
    elif route == "DATA_QUERY":
        result["needs_parser"] = True
        result["needs_db"] = True
        result["answer"] = None
    elif route == "FOLLOW_UP_ANALYSIS":
        result["needs_parser"] = False
        result["needs_db"] = False
        result["rewritten_query"] = None
    elif route == "NEED_CLARIFICATION":
        result["needs_parser"] = False
        result["needs_db"] = False
        result["rewritten_query"] = None
        result["clarification_question"] = (
            result["clarification_question"]
            or "Bạn muốn phân tích chỉ số, quốc gia và giai đoạn nào?"
        )
    elif route in {"UNSUPPORTED", "OFF_TOPIC"}:
        result["needs_parser"] = False
        result["needs_db"] = False
        result["rewritten_query"] = None

    return result


def _strip_code_fence(text: str) -> str:
    cleaned = str(text or "").strip()
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return cleaned


def _string_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item or "").strip()]
    return [str(value)]


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_upper(value: Any) -> str | None:
    text = _optional_str(value)
    return text.upper() if text else None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clamp_int(value: Any, min_value: int, max_value: int) -> int | None:
    number = _int_or_none(value)
    if number is None:
        return None
    return max(min_value, min(max_value, number))


def _ranking_order(value: Any) -> str | None:
    text = str(value or "").lower().strip()
    if text in {"asc", "desc"}:
        return text
    return None


def _clamp_float(value: Any, min_value: float, max_value: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = min_value
    return max(min_value, min(max_value, number))


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result
