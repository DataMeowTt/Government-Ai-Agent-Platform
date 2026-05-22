from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.parser.indicator_guard import validate_indicator_codes
from app.parser.model_adapter import (
    create_plan_from_model_parsed,
    model_intent_to_question_type,
    parsed_query_to_slots,
)
from app.parser.parser_service_client import call_parser_service
from app.planner.plan_schema import QueryPlan
from app.planner.query_planner import create_query_plan
from app.resolver.slot_resolver import ResolvedSlots, resolve_slots
from app.router.rule_router import classify_question


@dataclass(frozen=True)
class HybridParseResult:
    question_type: str
    slots: ResolvedSlots
    plan: QueryPlan
    parsed_query: dict[str, Any] | None
    parser_debug: dict[str, Any]
    status: str | None = None
    clarification_questions: list[str] | None = None


def parse_with_hybrid_parser(
    message: str,
    context: dict[str, Any] | None = None,
) -> HybridParseResult:
    if settings.parser_mode.lower() != "hybrid":
        return _rule_based_result(message, reason="parser_mode_not_hybrid")

    parser_response = call_parser_service(message, context=context)
    if parser_response is None:
        return _rule_based_result(
            message,
            reason="parser_service_error",
            parser_service_available=False,
        )

    parsed_query = parser_response.get("parsed")
    if not isinstance(parsed_query, dict):
        return _rule_based_result(
            message,
            reason=parser_response.get("fallback_reason") or "missing_parsed",
            parser_service_available=True,
            parser_response=parser_response,
        )

    parsed_query = _cleanup_parsed_query(parsed_query, parser_response)
    indicator_validation = validate_indicator_codes(parsed_query)
    intent = parsed_query.get("intent")
    parser_debug = _model_parser_debug(parser_response, indicator_validation)

    if not indicator_validation["valid"]:
        return _blocked_indicator_result(parsed_query, parser_debug, indicator_validation)

    if intent == "NEED_CLARIFICATION":
        slots = parsed_query_to_slots(parsed_query)
        questions = parsed_query.get("clarification_questions") or slots.clarification_questions
        plan = QueryPlan(
            question_type="NEED_CLARIFICATION",
            tool_name="none",
            arguments={},
            warnings=questions,
        )
        return HybridParseResult(
            question_type="NEED_CLARIFICATION",
            slots=slots,
            plan=plan,
            parsed_query=parsed_query,
            parser_debug=parser_debug,
            status="needs_clarification",
            clarification_questions=questions,
        )

    if intent in {"UNSUPPORTED", "OFF_TOPIC"}:
        slots = parsed_query_to_slots(parsed_query)
        question_type = model_intent_to_question_type(intent)
        plan = QueryPlan(
            question_type=question_type,
            tool_name="none",
            arguments={},
            warnings=[],
        )
        return HybridParseResult(
            question_type=question_type,
            slots=slots,
            plan=plan,
            parsed_query=parsed_query,
            parser_debug=parser_debug,
            status="unsupported" if intent == "UNSUPPORTED" else "off_topic",
        )

    if _can_use_model_parser(parser_response, parsed_query):
        slots = parsed_query_to_slots(parsed_query)
        plan = create_plan_from_model_parsed(parsed_query)
        return HybridParseResult(
            question_type=plan.question_type,
            slots=slots,
            plan=plan,
            parsed_query=parsed_query,
            parser_debug=parser_debug,
        )

    return _rule_based_result(
        message,
        reason=parser_response.get("fallback_reason") or _unsafe_reason(parser_response, parsed_query),
        parser_service_available=True,
        parser_response=parser_response,
    )


def _rule_based_result(
    message: str,
    reason: str,
    parser_service_available: bool | None = None,
    parser_response: dict[str, Any] | None = None,
) -> HybridParseResult:
    slots = resolve_slots(message)
    question_type = classify_question(message, slots)
    plan = create_query_plan(question_type, slots)
    parser_debug: dict[str, Any] = {
        "mode": settings.parser_mode,
        "source": "rule_based_fallback",
        "reason": reason,
        "fallback_reason": reason,
    }
    if parser_service_available is not None:
        parser_debug["parserServiceAvailable"] = parser_service_available
    if parser_response:
        parser_debug.update(
            {
                "safe_to_execute": parser_response.get("safe_to_execute"),
                "catalog_pass": parser_response.get("catalog_pass"),
                "schema_pass": parser_response.get("schema_pass"),
                "deployment_schema_pass": parser_response.get("deployment_schema_pass"),
                "latency_ms": parser_response.get("latency_ms"),
            }
        )

    return HybridParseResult(
        question_type=question_type,
        slots=slots,
        plan=plan,
        parsed_query=None,
        parser_debug=parser_debug,
    )


def _model_parser_debug(
    parser_response: dict[str, Any],
    indicator_validation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "mode": settings.parser_mode,
        "source": "model_parser",
        "safe_to_execute": parser_response.get("safe_to_execute"),
        "catalog_pass": parser_response.get("catalog_pass"),
        "schema_pass": parser_response.get("schema_pass"),
        "deployment_schema_pass": parser_response.get("deployment_schema_pass"),
        "fallback_reason": parser_response.get("fallback_reason"),
        "latency_ms": parser_response.get("latency_ms"),
        "inference_mode": parser_response.get("inference_mode"),
        "indicator_guard": indicator_validation,
    }


def _cleanup_parsed_query(
    parsed_query: dict[str, Any],
    parser_response: dict[str, Any],
) -> dict[str, Any]:
    cleaned = dict(parsed_query)
    if cleaned.get("intent") != "NEED_CLARIFICATION":
        return cleaned

    candidates = parser_response.get("candidates") or {}
    detected_years = candidates.get("detected_years") if isinstance(candidates, dict) else None
    fallback_reason = str(parser_response.get("fallback_reason") or "")

    should_clear_years = (
        detected_years == []
        or detected_years is None
        and any(
            reason in fallback_reason
            for reason in ("missing_indicator", "missing_time", "need_clarification")
        )
    )

    if should_clear_years:
        cleaned["start_year"] = None
        cleaned["end_year"] = None

    return cleaned


def _can_use_model_parser(
    parser_response: dict[str, Any],
    parsed_query: dict[str, Any],
) -> bool:
    allowed_intents = {
        item.strip()
        for item in settings.parser_hybrid_allowed_intents.split(",")
        if item.strip()
    }
    schema_pass = bool(
        parser_response.get("deployment_schema_pass")
        or parser_response.get("schema_pass")
    )
    indicator_validation = validate_indicator_codes(parsed_query)

    return (
        parser_response.get("safe_to_execute") is True
        and parser_response.get("catalog_pass") is True
        and schema_pass
        and indicator_validation["valid"]
        and parsed_query.get("intent") in allowed_intents
    )


def _unsafe_reason(
    parser_response: dict[str, Any],
    parsed_query: dict[str, Any],
) -> str:
    indicator_validation = validate_indicator_codes(parsed_query)
    if not indicator_validation["valid"]:
        return "invalid_indicator_in_parser_response"
    if parser_response.get("valid_json") is False:
        return "invalid_json"
    if not (parser_response.get("deployment_schema_pass") or parser_response.get("schema_pass")):
        return "schema_error"
    if parser_response.get("catalog_pass") is False:
        return "catalog_validation_failed"
    if parser_response.get("safe_to_execute") is not True:
        return "not_safe_to_execute"
    if parsed_query.get("intent") not in {
        item.strip()
        for item in settings.parser_hybrid_allowed_intents.split(",")
        if item.strip()
    }:
        return "intent_not_allowed"
    return "cannot_use_model_parser"


def _blocked_indicator_result(
    parsed_query: dict[str, Any],
    parser_debug: dict[str, Any],
    indicator_validation: dict[str, Any],
) -> HybridParseResult:
    problems: list[str] = []
    if indicator_validation["forbidden_indicators"]:
        problems.append(
            "technical indicators: "
            + ", ".join(indicator_validation["forbidden_indicators"])
        )
    if indicator_validation["unknown_indicators"]:
        problems.append(
            "unknown indicators: " + ", ".join(indicator_validation["unknown_indicators"])
        )

    warning_detail = "; ".join(problems) if problems else "invalid indicators"
    warning = (
        "Yêu cầu chưa thể thực thi an toàn vì parser trả chỉ số không hợp lệ "
        f"({warning_detail}). Vui lòng nêu chỉ số công khai trong catalog."
    )
    parser_debug["fallback_reason"] = "invalid_indicator_in_parser_response"

    plan = QueryPlan(
        question_type="UNSUPPORTED_DATA_QUERY",
        tool_name="none",
        arguments={},
        warnings=[warning],
    )
    return HybridParseResult(
        question_type="UNSUPPORTED_DATA_QUERY",
        slots=parsed_query_to_slots({"indicators": [], "countries": []}),
        plan=plan,
        parsed_query=parsed_query,
        parser_debug=parser_debug,
        status="unsupported",
    )
