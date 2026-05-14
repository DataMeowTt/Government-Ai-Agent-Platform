import re
from typing import Any

from app.catalog.canonical_indicator_catalog import (
    normalize_catalog_text,
    resolve_indicator_alias,
)
from app.catalog.country_group_catalog import resolve_country_groups
from app.pipeline.schemas import RuleRouteDraft
from app.resolver.country_resolver import resolve_countries


ANALYSIS_MARKERS = (
    "vi sao",
    "tai sao",
    "ly do",
    "nguyen nhan",
    "phan tich",
    "nhan xet",
    "insight",
    "diem chung",
    "rui ro",
    "tom tat",
    "dien giai",
    "ket luan",
    "y nghia",
)

CONTEXT_REFERENCE_MARKERS = (
    "nay",
    "do",
    "tren",
    "nhom nay",
    "cac nuoc nay",
    "ket qua",
    "bang",
    "bieu do",
    "xu huong",
)

MODIFY_MARKERS = (
    "them",
    "bo",
    "xoa",
    "doi",
    "thay",
    "chi lay",
    "cho them",
    "top",
    "thap nhat",
    "cao nhat",
    "tu nam",
    "den nam",
    "giai doan",
)

DEFINITION_MARKERS = (
    "la gi",
    "la chi so gi",
    "chi so gi",
    "nghia la gi",
    "y nghia",
    "cach hieu",
    "dung de",
    "phan anh dieu gi",
    "phan anh gi",
    "cho biet dieu gi",
    "dung de danh gia",
    "noi len dieu gi",
    "the hien dieu gi",
    "khac gi",
    "what is",
    "definition",
    "define",
)

COVERAGE_MARKERS = (
    "coverage",
    "co bao nhieu quan sat",
    "co du lieu khong",
    "thieu du lieu",
    "phu du lieu",
    "pham vi du lieu",
    "du lieu co tu",
)

COMPARE_MARKERS = (
    "so sanh",
    "compare",
    " vs ",
    "voi",
    "giua",
)

RANKING_MARKERS = (
    "top",
    "cao nhat",
    "thap nhat",
    "xep hang",
    "ranking",
    "highest",
    "lowest",
)

TREND_MARKERS = (
    "xu huong",
    "trend",
    "qua cac nam",
    "theo thoi gian",
    "giai doan",
)

ANOMALY_MARKERS = (
    "bat thuong",
    "anomaly",
    "outlier",
)

DATA_QUERY_MARKERS = (
    *COVERAGE_MARKERS,
    *COMPARE_MARKERS,
    *RANKING_MARKERS,
    *TREND_MARKERS,
    *ANOMALY_MARKERS,
    "du lieu",
    "tu nam",
    "den nam",
)

OFF_TOPIC_MARKERS = (
    "thoi tiet",
    "weather",
    "viet tho",
    "ke chuyen",
    "nau an",
    "world cup",
    "bong da",
    "vo dich world cup",
    "co phieu",
    "chung khoan",
    "tu van mua co phieu",
    "mua co phieu",
    "du bao",
    "du doan",
    "forecast",
    "prediction",
    "predict",
    "arima",
    "train model",
    "huan luyen model",
    "viet sql",
    "xoa bang",
    "delete table",
    "drop table",
)

def run_rule_first_router(
    user_message: str,
    conversation_context: dict[str, Any] | None = None,
) -> RuleRouteDraft:
    context = conversation_context or {}
    normalized = normalize_catalog_text(user_message)
    indicator_match = resolve_indicator_alias(user_message)
    country_groups = [match.group.code for match in resolve_country_groups(user_message)]
    countries = [match.country.code for match in resolve_countries(user_message)]
    years = _extract_years(normalized)
    limit = _extract_limit(normalized)
    ranking_order = _extract_order(normalized)

    has_previous_result = _has_previous_result(context)
    has_previous_query = _has_previous_query(context)
    has_new_data_slots = _has_new_data_slots(
        indicator_match=indicator_match,
        countries=countries,
        country_groups=country_groups,
        years=years,
        limit=limit,
        ranking_order=ranking_order,
    )
    has_definition_marker = _has_definition_marker(normalized)
    has_analysis_marker = _has_analysis_marker(normalized)
    has_modify_marker = _has_modify_marker(normalized)
    has_context_reference_marker = _has_context_reference_marker(normalized)
    has_data_query_marker = _has_data_query_marker(normalized)
    has_coverage_marker = _contains_any(normalized, COVERAGE_MARKERS)
    has_compare_marker = _contains_any(normalized, COMPARE_MARKERS)
    has_ranking_marker = _contains_any(normalized, RANKING_MARKERS)
    has_anomaly_marker = _contains_any(normalized, ANOMALY_MARKERS)
    has_trend_marker = _contains_any(normalized, TREND_MARKERS)

    if _contains_any(normalized, OFF_TOPIC_MARKERS):
        return RuleRouteDraft(
            matched=True,
            route="DATA_QUERY",
            confidence=0.35,
            needs_front_llm=True,
            needs_parser_agent=False,
            needs_db=False,
            reason="possible_off_topic_needs_front_llm",
        )

    if (
        has_definition_marker
        and indicator_match
        and not countries
        and not country_groups
        and not years
        and not has_data_query_marker
    ):
        return RuleRouteDraft(
            matched=True,
            route="GENERAL_EXPLANATION",
            confidence=0.95,
            needs_front_llm=False,
            needs_parser_agent=False,
            needs_db=False,
            intent_hint="GENERAL_EXPLANATION",
            draft_indicators=[indicator_match.indicator.code],
            reason="Definition query matched without data slots or data-query markers.",
        )

    if (
        has_previous_result
        and (has_analysis_marker or has_context_reference_marker)
        and not has_modify_marker
        and not has_new_data_slots
    ):
        return RuleRouteDraft(
            matched=True,
            route="DATA_QUERY",
            confidence=0.55,
            needs_front_llm=True,
            needs_parser_agent=False,
            needs_db=False,
            uses_previous_context=True,
            reason="possible_follow_up_analysis_needs_front_llm",
        )

    if has_previous_result and (has_analysis_marker or has_context_reference_marker) and has_new_data_slots:
        return _safe_low_confidence_draft(
            indicator_match=indicator_match,
            countries=countries,
            country_groups=country_groups,
            years=years,
            limit=limit,
            ranking_order=ranking_order,
            confidence=0.7,
            uses_previous_context=True,
            intent_hint=_infer_intent_hint(normalized, indicator_match, countries, country_groups),
            reason="Follow-up analysis signal also contains new data slots; defer to Front LLM / Parser Agent.",
        )

    delta = _extract_delta(normalized, countries)
    clear_delta = bool(delta)
    if has_previous_query and (has_modify_marker or clear_delta):
        if clear_delta:
            return RuleRouteDraft(
                matched=True,
                route="FOLLOW_UP_MODIFY_QUERY",
                confidence=0.9,
                needs_front_llm=False,
                needs_parser_agent=True,
                needs_db=True,
                uses_previous_context=True,
                draft_countries=countries,
                draft_start_year=years[0] if years else None,
                draft_end_year=years[-1] if years else None,
                draft_limit=limit,
                draft_ranking_order=ranking_order,
                delta=delta,
                reason="Follow-up query modification matched previous query with explicit delta.",
            )
        return _safe_low_confidence_draft(
            indicator_match=indicator_match,
            countries=countries,
            country_groups=country_groups,
            years=years,
            limit=limit,
            ranking_order=ranking_order,
            confidence=0.7,
            uses_previous_context=True,
            intent_hint=_infer_intent_hint(normalized, indicator_match, countries, country_groups),
            reason="Modify signal matched previous query but delta is ambiguous; defer to Front LLM / Parser Agent.",
        )

    if has_coverage_marker:
        if indicator_match:
            return _build_data_draft(
                intent_hint="COVERAGE",
                indicator_match=indicator_match,
                countries=countries,
                country_groups=country_groups,
                years=years,
                limit=limit,
                ranking_order=ranking_order,
                confidence=0.9,
                needs_front_llm=False,
                reason="Coverage marker matched with a supported indicator.",
            )
        return _safe_low_confidence_draft(
            indicator_match=indicator_match,
            countries=countries,
            country_groups=country_groups,
            years=years,
            limit=limit,
            ranking_order=ranking_order,
            confidence=0.65,
            intent_hint="COVERAGE",
            reason="Coverage marker lacks a deterministic indicator; defer to Front LLM / Parser Agent.",
        )

    if has_compare_marker:
        if indicator_match and (len(countries) >= 2 or country_groups):
            return _build_data_draft(
                intent_hint="COMPARE_COUNTRIES",
                indicator_match=indicator_match,
                countries=countries,
                country_groups=country_groups,
                years=years,
                limit=limit,
                ranking_order=ranking_order,
                confidence=0.92,
                needs_front_llm=False,
                reason="Compare marker matched with indicator and compare slots.",
            )
        return _safe_low_confidence_draft(
            indicator_match=indicator_match,
            countries=countries,
            country_groups=country_groups,
            years=years,
            limit=limit,
            ranking_order=ranking_order,
            confidence=0.65,
            intent_hint="COMPARE_COUNTRIES",
            reason="Compare marker lacks enough deterministic slots; defer to Front LLM / Parser Agent.",
        )

    if indicator_match and has_ranking_marker:
        if not years:
            return _safe_low_confidence_draft(
                indicator_match=indicator_match,
                countries=countries,
                country_groups=country_groups,
                years=years,
                limit=limit,
                ranking_order=ranking_order,
                confidence=0.65,
                intent_hint="RANKING",
                reason="Ranking marker lacks an explicit year; defer to Front LLM for context rewrite or clarification.",
            )
        return _build_data_draft(
            intent_hint="RANKING",
            indicator_match=indicator_match,
            countries=countries,
            country_groups=country_groups,
            years=years,
            limit=limit or 10,
            ranking_order=ranking_order or "desc",
            confidence=0.9,
            needs_front_llm=False,
            reason="Ranking marker matched with a supported indicator.",
        )

    if indicator_match and has_anomaly_marker:
        return _build_data_draft(
            intent_hint="ANOMALY_DETECTION",
            indicator_match=indicator_match,
            countries=countries,
            country_groups=country_groups,
            years=years,
            limit=limit,
            ranking_order=ranking_order,
            confidence=0.9,
            needs_front_llm=False,
            reason="Anomaly marker matched with a supported indicator.",
        )

    if indicator_match and (countries or country_groups) and (years or has_trend_marker):
        return _build_data_draft(
            intent_hint="TREND_ANALYSIS" if has_trend_marker else "TIME_SERIES",
            indicator_match=indicator_match,
            countries=countries,
            country_groups=country_groups,
            years=years,
            limit=limit,
            ranking_order=ranking_order,
            confidence=0.9 if has_trend_marker else 0.88,
            needs_front_llm=not has_trend_marker,
            reason="Time-series data signal matched with indicator and country slots.",
        )

    if indicator_match and (countries or country_groups):
        return _build_data_draft(
            intent_hint="VALUE_LOOKUP",
            indicator_match=indicator_match,
            countries=countries,
            country_groups=country_groups,
            years=years,
            limit=limit,
            ranking_order=ranking_order,
            confidence=0.75,
            needs_front_llm=True,
            reason="Indicator and country slots matched without enough intent context; defer to Front LLM / Parser Agent.",
        )

    if has_data_query_marker or indicator_match or has_new_data_slots:
        return _safe_low_confidence_draft(
            indicator_match=indicator_match,
            countries=countries,
            country_groups=country_groups,
            years=years,
            limit=limit,
            ranking_order=ranking_order,
            confidence=0.65,
            intent_hint=_infer_intent_hint(normalized, indicator_match, countries, country_groups),
            reason="Low-confidence deterministic signals only; defer to Front LLM / Parser Agent.",
        )

    return RuleRouteDraft(
        matched=False,
        confidence=0.0,
        needs_front_llm=True,
        needs_parser_agent=True,
        needs_db=True,
        reason="No reliable deterministic route matched; defer to Front LLM / Parser Agent.",
    )


def _has_previous_result(context: dict[str, Any]) -> bool:
    return bool(
        context.get("last_data_query")
        or context.get("last_rows")
        or context.get("last_result_summary")
        or context.get("last_data_summary")
        or context.get("last_result_validation")
    )


def _has_previous_query(context: dict[str, Any]) -> bool:
    return bool(
        context.get("last_data_query")
        or context.get("last_parsed_query")
        or context.get("last_validated_query")
        or context.get("last_query_plan")
    )


def _has_new_data_slots(
    indicator_match: Any,
    countries: list[str],
    country_groups: list[str],
    years: list[int],
    limit: int | None,
    ranking_order: str | None,
) -> bool:
    return bool(indicator_match or countries or country_groups or years or limit or ranking_order)


def _has_data_query_marker(normalized: str) -> bool:
    return _contains_any(normalized, DATA_QUERY_MARKERS)


def _has_definition_marker(normalized: str) -> bool:
    return _contains_any(normalized, DEFINITION_MARKERS)


def _has_analysis_marker(normalized: str) -> bool:
    return _contains_any(normalized, ANALYSIS_MARKERS)


def _has_modify_marker(normalized: str) -> bool:
    return _contains_any(normalized, MODIFY_MARKERS)


def _has_context_reference_marker(normalized: str) -> bool:
    return _contains_any(normalized, CONTEXT_REFERENCE_MARKERS)


def _infer_intent_hint(
    normalized: str,
    indicator_match: Any,
    countries: list[str],
    country_groups: list[str],
) -> str | None:
    if _contains_any(normalized, COVERAGE_MARKERS):
        return "COVERAGE"
    if _contains_any(normalized, COMPARE_MARKERS):
        return "COMPARE_COUNTRIES"
    if _contains_any(normalized, RANKING_MARKERS):
        return "RANKING"
    if _contains_any(normalized, ANOMALY_MARKERS):
        return "ANOMALY_DETECTION"
    if _contains_any(normalized, TREND_MARKERS):
        return "TREND_ANALYSIS"
    if indicator_match and (countries or country_groups):
        return "TIME_SERIES"
    if indicator_match:
        return "VALUE_LOOKUP"
    return None


def _build_data_draft(
    *,
    intent_hint: str,
    indicator_match: Any,
    countries: list[str],
    country_groups: list[str],
    years: list[int],
    limit: int | None,
    ranking_order: str | None,
    confidence: float,
    needs_front_llm: bool,
    reason: str,
) -> RuleRouteDraft:
    return RuleRouteDraft(
        matched=True,
        route="DATA_QUERY",
        confidence=confidence,
        needs_front_llm=needs_front_llm,
        needs_parser_agent=True,
        needs_db=True,
        intent_hint=intent_hint,
        draft_indicators=[indicator_match.indicator.code] if indicator_match else [],
        draft_countries=countries,
        draft_country_groups=country_groups,
        draft_start_year=years[0] if years else None,
        draft_end_year=years[-1] if years else None,
        draft_limit=limit,
        draft_ranking_order=ranking_order,
        reason=reason,
    )


def _safe_low_confidence_draft(
    *,
    indicator_match: Any,
    countries: list[str],
    country_groups: list[str],
    years: list[int],
    limit: int | None,
    ranking_order: str | None,
    confidence: float = 0.65,
    uses_previous_context: bool = False,
    intent_hint: str | None = None,
    reason: str = "Low-confidence deterministic signals only; defer to Front LLM / Parser Agent.",
) -> RuleRouteDraft:
    return RuleRouteDraft(
        matched=True,
        route="DATA_QUERY" if (indicator_match or countries or country_groups or years or limit or ranking_order or intent_hint) else None,
        confidence=confidence,
        needs_front_llm=True,
        needs_parser_agent=True,
        needs_db=True,
        uses_previous_context=uses_previous_context,
        intent_hint=intent_hint,
        draft_indicators=[indicator_match.indicator.code] if indicator_match else [],
        draft_countries=countries,
        draft_country_groups=country_groups,
        draft_start_year=years[0] if years else None,
        draft_end_year=years[-1] if years else None,
        draft_limit=limit,
        draft_ranking_order=ranking_order,
        reason=reason,
    )


def _contains_any(normalized_text: str, keywords: tuple[str, ...]) -> bool:
    padded = f" {normalized_text} "

    for keyword in keywords:
        key = str(keyword or "").strip()
        if not key:
            continue

        if len(key) <= 3:
            if re.search(rf"(^|\s){re.escape(key)}($|\s)", normalized_text):
                return True
            continue
        if " " in key:
            if f" {key} " in padded:
                return True
            continue
        if key in normalized_text:
            return True

    return False
def _extract_years(normalized_text: str) -> list[int]:
    years: list[int] = []
    for raw_year in re.findall(r"\b((?:19|20)\d{2})\b", normalized_text):
        year = int(raw_year)
        if year not in years:
            years.append(year)
    return years


def _extract_limit(normalized_text: str) -> int | None:
    match = re.search(r"\btop\s+(\d+)\b", normalized_text)
    if not match:
        return None
    return max(1, min(int(match.group(1)), 50))


def _extract_order(normalized_text: str) -> str | None:
    if any(token in normalized_text for token in ("thap nhat", "lowest", "nho nhat")):
        return "asc"
    if any(token in normalized_text for token in ("cao nhat", "highest", "lon nhat", "top")):
        return "desc"
    return None


def _extract_delta(normalized_text: str, countries: list[str]) -> dict[str, Any]:
    delta: dict[str, Any] = {}
    years = _extract_years(normalized_text)
    if years:
        delta["year"] = years[-1] if len(years) == 1 else None
        delta["start_year"] = years[0]
        delta["end_year"] = years[-1]
    limit = _extract_limit(normalized_text)
    if limit is not None:
        delta["limit"] = limit
    ranking_order = _extract_order(normalized_text)
    if ranking_order:
        delta["ranking_order"] = ranking_order
    if countries and "them" in normalized_text:
        delta["add_countries"] = countries
    elif countries and ("bo" in normalized_text or "xoa" in normalized_text):
        delta["remove_countries"] = countries
    elif countries:
        delta["countries"] = countries
    return {key: value for key, value in delta.items() if value is not None}
