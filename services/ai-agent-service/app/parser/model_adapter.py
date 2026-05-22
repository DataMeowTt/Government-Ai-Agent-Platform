from dataclasses import asdict
from typing import Any

from app.catalog.analytics_catalog import get_indicator_analytics_metadata
from app.catalog.indicator_catalog import get_indicator
from app.planner.plan_schema import QueryPlan
from app.planner.query_planner import create_query_plan
from app.resolver.country_resolver import COUNTRIES
from app.resolver.slot_resolver import ResolvedSlots


MODEL_INTENT_TO_QUESTION_TYPE = {
    "COMPARE_COUNTRIES": "VALID_COMPARE_QUERY",
    "COMPARE_INDICATORS": "VALID_COMPARE_QUERY",
    "RANKING": "VALID_RANKING_QUERY",
    "RANK_BY_CHANGE": "VALID_RANKING_QUERY",
    "TIME_SERIES": "VALID_TREND_QUERY",
    "TREND_ANALYSIS": "VALID_TREND_QUERY",
    "VALUE_LOOKUP": "VALID_TREND_QUERY",
    "COVERAGE": "VALID_COVERAGE_QUERY",
    "ANOMALY_DETECTION": "VALID_ANOMALY_QUERY",
    "NEED_CLARIFICATION": "NEED_CLARIFICATION",
    "UNSUPPORTED": "UNSUPPORTED",
    "OFF_TOPIC": "OFF_TOPIC",
}


def model_intent_to_question_type(intent: str | None) -> str:
    return MODEL_INTENT_TO_QUESTION_TYPE.get(intent or "", "UNSUPPORTED_DATA_QUERY")


def parsed_query_to_slots(parsed_query: dict[str, Any]) -> ResolvedSlots:
    indicators = []
    for code in parsed_query.get("indicators") or []:
        indicator = _indicator_to_slot(code)
        if indicator is not None:
            indicators.append(indicator)

    countries = []
    for code in parsed_query.get("countries") or []:
        country = _country_to_slot(code)
        if country is not None:
            countries.append(country)

    start_year = parsed_query.get("start_year")
    end_year = parsed_query.get("end_year")
    years = [year for year in (start_year, end_year) if isinstance(year, int)]
    years = sorted(set(years))

    clarification_questions = parsed_query.get("clarification_questions") or []
    needs_clarification = bool(
        parsed_query.get("needs_clarification")
        or parsed_query.get("intent") == "NEED_CLARIFICATION"
        or clarification_questions
    )

    return ResolvedSlots(
        indicators=indicators,
        countries=countries,
        start_year=start_year if isinstance(start_year, int) else None,
        end_year=end_year if isinstance(end_year, int) else None,
        years=years,
        needs_clarification=needs_clarification,
        clarification_questions=clarification_questions,
    )


def create_plan_from_model_parsed(parsed_query: dict[str, Any]) -> QueryPlan:
    question_type = model_intent_to_question_type(parsed_query.get("intent"))
    slots = parsed_query_to_slots(parsed_query)
    plan = create_query_plan(question_type, slots)

    if plan.question_type == "VALID_RANKING_QUERY":
        arguments = dict(plan.arguments)
        limit = _int_or_none(parsed_query.get("limit"))
        if limit is not None:
            arguments["limit"] = limit
        if parsed_query.get("ranking_order") in {"asc", "desc"}:
            arguments["order"] = parsed_query["ranking_order"]
        return QueryPlan(
            question_type=plan.question_type,
            tool_name=plan.tool_name,
            arguments=arguments,
            warnings=plan.warnings,
        )

    if plan.question_type == "VALID_ANOMALY_QUERY":
        arguments = dict(plan.arguments)
        threshold = _float_or_none(parsed_query.get("threshold"))
        limit = _int_or_none(parsed_query.get("limit"))
        if threshold is not None:
            arguments["threshold"] = threshold
        if limit is not None:
            arguments["limit"] = limit
        return QueryPlan(
            question_type=plan.question_type,
            tool_name=plan.tool_name,
            arguments=arguments,
            warnings=plan.warnings,
        )

    return plan


def _indicator_to_slot(code: str) -> dict[str, Any] | None:
    indicator = get_indicator(code)
    if indicator is None:
        return None

    data = asdict(indicator)
    analytics_metadata = get_indicator_analytics_metadata(indicator.code)
    data["confidence"] = 1.0
    data["matched_alias"] = indicator.code
    data["analytics"] = analytics_metadata
    if analytics_metadata["analytics_table"]:
        data["analytics_table"] = analytics_metadata["analytics_table"]
    return data


def _country_to_slot(code: str) -> dict[str, Any] | None:
    country = COUNTRIES.get(code)
    if country is None:
        return None

    data = asdict(country)
    data["matched_alias"] = country.code
    return data


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
