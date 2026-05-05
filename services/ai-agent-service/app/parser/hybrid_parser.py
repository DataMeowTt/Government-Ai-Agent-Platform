from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.parser.model_adapter import (
    create_plan_from_model_parsed,
    model_intent_to_question_type,
    parsed_query_to_slots,
)
from app.parser.parser_service_client import call_parser_service
from app.planner.plan_schema import QueryPlan
from app.planner.query_planner import create_query_plan
from app.resolver.slot_resolver import ResolvedSlots, resolve_slots
from app.resolver.indicator_resolver import detect_unsupported_indicator_label
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
    unsupported_label = _unsupported_indicator_label(message, parsed_query)
    if unsupported_label:
        return _unsupported_indicator_result(
            message=message,
            label=unsupported_label,
            parser_debug=_model_parser_debug(parser_response),
            parsed_query=parsed_query,
        )

    intent = parsed_query.get("intent")
    parser_debug = _model_parser_debug(parser_response)

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
    unsupported_label = detect_unsupported_indicator_label(message)
    if unsupported_label:
        parser_debug: dict[str, Any] = {
            "mode": settings.parser_mode,
            "source": "rule_based_fallback",
            "reason": reason,
            "fallback_reason": reason,
        }
        if parser_service_available is not None:
            parser_debug["parserServiceAvailable"] = parser_service_available
        return _unsupported_indicator_result(
            message=message,
            label=unsupported_label,
            parser_debug=parser_debug,
            parsed_query=None,
        )

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


def _unsupported_indicator_label(message: str, parsed_query: dict[str, Any]) -> str | None:
    label = detect_unsupported_indicator_label(message)
    if label:
        return label
    for code in parsed_query.get("indicators") or []:
        label = detect_unsupported_indicator_label(str(code))
        if label:
            return label
    return None


def _unsupported_indicator_result(
    message: str,
    label: str,
    parser_debug: dict[str, Any],
    parsed_query: dict[str, Any] | None,
) -> HybridParseResult:
    resolved = resolve_slots(message)
    slots = ResolvedSlots(
        indicators=[],
        countries=resolved.countries,
        start_year=resolved.start_year,
        end_year=resolved.end_year,
        years=resolved.years,
        needs_clarification=False,
        clarification_questions=[],
    )
    warning = f"Hiện hệ thống chưa có chỉ số {label} trong dữ liệu hiện có."
    plan = QueryPlan(
        question_type="UNSUPPORTED_DATA_QUERY",
        tool_name="none",
        arguments={},
        warnings=[warning],
    )
    cleaned_parsed = dict(parsed_query or {})
    cleaned_parsed["intent"] = "UNSUPPORTED"
    cleaned_parsed["unsupported_indicator"] = label
    cleaned_parsed["needs_clarification"] = False
    cleaned_parsed["clarification_questions"] = []
    return HybridParseResult(
        question_type="UNSUPPORTED_DATA_QUERY",
        slots=slots,
        plan=plan,
        parsed_query=cleaned_parsed,
        parser_debug=parser_debug,
        status="unsupported",
    )


def _model_parser_debug(parser_response: dict[str, Any]) -> dict[str, Any]:
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

    return (
        parser_response.get("safe_to_execute") is True
        and parser_response.get("catalog_pass") is True
        and schema_pass
        and parsed_query.get("intent") in allowed_intents
    )


def _unsafe_reason(
    parser_response: dict[str, Any],
    parsed_query: dict[str, Any],
) -> str:
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
