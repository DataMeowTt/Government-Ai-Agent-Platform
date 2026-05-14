from typing import Any

from app.catalog.canonical_indicator_catalog import (
    get_indicator,
    indicator_supports_anomaly,
    indicator_supports_trend,
    is_supported_indicator,
    normalize_catalog_text,
    resolve_indicator_alias,
)
from app.catalog.country_group_catalog import expand_country_groups, get_country_group
from app.pipeline.schemas import ParsedQueryCandidate, ValidationOutcome
from app.resolver.country_resolver import COUNTRIES


ALLOWED_ROUTES = {
    "DIRECT_ANSWER",
    "GENERAL_EXPLANATION",
    "DATA_QUERY",
    "FOLLOW_UP_ANALYSIS",
    "FOLLOW_UP_MODIFY_QUERY",
    "NEED_CLARIFICATION",
    "UNSUPPORTED",
    "OFF_TOPIC",
}

ALLOWED_INTENTS = {
    "COMPARE_COUNTRIES",
    "RANKING",
    "TIME_SERIES",
    "TREND_ANALYSIS",
    "ANOMALY_DETECTION",
    "COVERAGE",
    "VALUE_LOOKUP",
    "NEED_CLARIFICATION",
    "UNSUPPORTED",
    "OFF_TOPIC",
    "DIRECT_ANSWER",
    "GENERAL_EXPLANATION",
}

DATA_QUERY_INTENTS = {
    "COMPARE_COUNTRIES",
    "RANKING",
    "TIME_SERIES",
    "TREND_ANALYSIS",
    "ANOMALY_DETECTION",
    "COVERAGE",
    "VALUE_LOOKUP",
}


def validate_parsed_candidate(candidate: ParsedQueryCandidate) -> ValidationOutcome:
    route = candidate.route if candidate.route in ALLOWED_ROUTES else "DATA_QUERY"
    intent = candidate.intent if candidate.intent in ALLOWED_INTENTS else "NEED_CLARIFICATION"
    normalized_route = _normalize_route_for_intent(route, intent)
    unsupported_terms = list(candidate.unsupported_terms)
    warnings: list[str] = []
    indicators = _normalize_indicators(candidate.indicators, unsupported_terms)

    if unsupported_terms or intent == "UNSUPPORTED":
        return ValidationOutcome(
            ok=False,
            status="unsupported",
            question_type="UNSUPPORTED_DATA_QUERY",
            validated_query=None,
            unsupported_terms=_dedupe(unsupported_terms),
            reason="Requested indicator or capability is not supported by the current data catalog.",
        )

    if intent in {"DIRECT_ANSWER", "GENERAL_EXPLANATION"}:
        return ValidationOutcome(
            ok=True,
            status="success",
            question_type="VALID_SIMPLE_QUERY",
            validated_query={
                "route": normalized_route,
                "intent": intent,
                "indicator": None,
                "indicators": [],
                "countries": [],
                "country_groups": [],
                "start_year": None,
                "end_year": None,
                "effective_start_year": None,
                "effective_end_year": None,
                "limit": None,
                "ranking_order": None,
                "warnings": [],
            },
            reason="Non-data explanation route validated.",
        )

    if intent == "OFF_TOPIC":
        return ValidationOutcome(
            ok=True,
            status="off_topic",
            question_type="OFF_TOPIC",
            validated_query={
                "route": normalized_route,
                "intent": intent,
                "indicator": None,
                "indicators": [],
                "countries": [],
                "country_groups": [],
                "start_year": None,
                "end_year": None,
                "effective_start_year": None,
                "effective_end_year": None,
                "limit": None,
                "ranking_order": None,
                "warnings": [],
            },
            reason="Off-topic route validated.",
        )

    if intent in DATA_QUERY_INTENTS and not indicators:
        return _needs_indicator()

    for indicator_code in indicators:
        if not is_supported_indicator(indicator_code):
            return ValidationOutcome(
                ok=False,
                status="unsupported",
                question_type="UNSUPPORTED_DATA_QUERY",
                validated_query=None,
                unsupported_terms=[indicator_code],
                reason=f"Indicator {indicator_code} is not supported by canonical catalog.",
            )

    indicator_code = indicators[0] if indicators else None
    indicator = get_indicator(indicator_code) if indicator_code else None

    valid_groups, invalid_groups = _normalize_country_groups(candidate.country_groups)
    if invalid_groups:
        warnings.append("Một số nhóm quốc gia không hợp lệ đã được bỏ qua: " + ", ".join(invalid_groups) + ".")

    raw_countries = _dedupe([*candidate.countries, *expand_country_groups(valid_groups)])
    countries, invalid_countries = _normalize_country_codes(raw_countries)
    if invalid_countries:
        warnings.append("Một số mã quốc gia không hợp lệ đã được bỏ qua: " + ", ".join(invalid_countries) + ".")

    if candidate.start_year is not None and candidate.end_year is not None and candidate.start_year > candidate.end_year:
        return ValidationOutcome(
            ok=False,
            status="needs_clarification",
            question_type="NEED_CLARIFICATION",
            validated_query=None,
            warnings=warnings,
            clarification_questions=["Khoảng thời gian chưa hợp lệ. Bạn muốn xem từ năm nào đến năm nào?"],
            reason="start_year greater than end_year.",
        )

    start_year, end_year, effective_start_year, effective_end_year, year_warnings, no_data_reason = _validate_years(
        candidate.start_year,
        candidate.end_year,
    )
    warnings.extend(year_warnings)

    if no_data_reason:
        return ValidationOutcome(
            ok=False,
            status="no_data",
            question_type="NO_DATA",
            validated_query={
                "route": normalized_route,
                "intent": intent,
                "indicator": indicator_code,
                "indicators": [indicator_code] if indicator_code else [],
                "countries": countries,
                "country_groups": valid_groups,
                "start_year": start_year,
                "end_year": end_year,
                "effective_start_year": effective_start_year,
                "effective_end_year": effective_end_year,
                "limit": candidate.limit,
                "ranking_order": candidate.ranking_order,
                "warnings": warnings,
            },
            warnings=warnings,
            reason=no_data_reason,
        )

    if intent == "COMPARE_COUNTRIES" and len(countries) < 2:
        return ValidationOutcome(
            ok=False,
            status="needs_clarification",
            question_type="NEED_CLARIFICATION",
            validated_query=None,
            warnings=warnings,
            clarification_questions=["Bạn muốn so sánh những quốc gia hoặc nhóm quốc gia nào?"],
            reason="Compare query requires at least two countries after group expansion.",
        )

    if intent in {"TIME_SERIES", "TREND_ANALYSIS", "VALUE_LOOKUP"} and not countries:
        return ValidationOutcome(
            ok=False,
            status="needs_clarification",
            question_type="NEED_CLARIFICATION",
            validated_query=None,
            warnings=warnings,
            clarification_questions=["Bạn muốn xem cho quốc gia hoặc nhóm quốc gia nào?"],
            reason="Series query requires country.",
        )

    if intent == "ANOMALY_DETECTION" and indicator_code and not indicator_supports_anomaly(indicator_code):
        return ValidationOutcome(
            ok=False,
            status="unsupported",
            question_type="UNSUPPORTED_DATA_QUERY",
            validated_query=None,
            unsupported_terms=[indicator.name_vi if indicator else indicator_code],
            reason="Có dữ liệu gốc nhưng chưa có điểm bất thường cho chỉ số này.",
        )

    question_type = _question_type(intent, indicator_code, warnings)

    if intent == "RANKING":
        if effective_end_year is None and effective_start_year is None:
            return ValidationOutcome(
                ok=False,
                status="needs_clarification",
                question_type="NEED_CLARIFICATION",
                validated_query=None,
                warnings=warnings,
                clarification_questions=["Bạn muốn xếp hạng theo năm nào?"],
                reason="Ranking query requires an explicit or context-rewritten year.",
            )
        elif effective_end_year is None:
            effective_end_year = effective_start_year
        elif effective_start_year is None:
            effective_start_year = effective_end_year

    if intent == "TREND_ANALYSIS" and indicator_code and not indicator_supports_trend(indicator_code):
        warnings.append("Chỉ có dữ liệu gốc, chưa có analytics trend cho chỉ số này.")

    limit = _clamp(candidate.limit, 1, 50) if candidate.limit is not None else None
    if intent == "RANKING" and limit is None:
        limit = 10

    ranking_order = candidate.ranking_order if candidate.ranking_order in {"asc", "desc"} else None
    if intent == "RANKING" and ranking_order is None:
        ranking_order = "desc"

    validated_query = {
        "route": normalized_route,
        "intent": intent,
        "indicator": indicator_code,
        "indicators": [indicator_code] if indicator_code else [],
        "countries": countries,
        "country_groups": valid_groups,
        "start_year": start_year,
        "end_year": end_year,
        "effective_start_year": effective_start_year,
        "effective_end_year": effective_end_year,
        "limit": limit,
        "ranking_order": ranking_order,
        "warnings": warnings,
    }

    return ValidationOutcome(
        ok=True,
        status="success",
        question_type=question_type,
        validated_query=validated_query,
        warnings=warnings,
        reason="Candidate validated against canonical catalog.",
    )


def _needs_indicator() -> ValidationOutcome:
    question = "Bạn muốn phân tích chỉ số nào? Ví dụ: nợ công/GDP, lạm phát CPI, thất nghiệp, tăng trưởng GDP thực."
    return ValidationOutcome(
        ok=False,
        status="needs_clarification",
        question_type="NEED_CLARIFICATION",
        validated_query=None,
        clarification_questions=[question],
        reason="Data query requires indicator.",
    )


def _normalize_indicators(raw_indicators: list[Any], unsupported_terms: list[str]) -> list[str]:
    indicators: list[str] = []
    for raw in raw_indicators or []:
        text = str(raw or "").strip()
        if not text:
            continue

        normalized = normalize_catalog_text(text)
        alias_override = {
            "trade open pct gdp": "trade_pct_gdp",
            "trade openness": "trade_pct_gdp",
            "trade pct gdp": "trade_pct_gdp",
            "trade to gdp": "trade_pct_gdp",
            "gdp pc": "log_rGDP_pc_USD",
            "gdp per capita": "log_rGDP_pc_USD",
            "real gdp per capita": "log_rGDP_pc_USD",
        }.get(normalized)
        if alias_override:
            _append_unique(indicators, alias_override)
            continue

        if is_supported_indicator(text):
            _append_unique(indicators, text)
            continue

        alias_match = resolve_indicator_alias(text)
        if alias_match and is_supported_indicator(alias_match.indicator.code):
            _append_unique(indicators, alias_match.indicator.code)
            continue

        _append_unique(indicators, text)
    return indicators


def _question_type(intent: str, indicator_code: str | None, warnings: list[str]) -> str:
    if intent == "COMPARE_COUNTRIES":
        return "VALID_COMPARE_QUERY"
    if intent == "RANKING":
        return "VALID_RANKING_QUERY"
    if intent == "COVERAGE":
        return "VALID_COVERAGE_QUERY"
    if intent == "ANOMALY_DETECTION":
        return "VALID_ANOMALY_QUERY"
    if intent in {"TIME_SERIES", "TREND_ANALYSIS", "VALUE_LOOKUP"}:
        return "VALID_TREND_QUERY"
    if not indicator_code:
        return "NEED_CLARIFICATION"
    warnings.append("Dạng yêu cầu chưa rõ, hệ thống dùng chuỗi thời gian dữ liệu gốc.")
    return "VALID_TREND_QUERY"


def _normalize_route_for_intent(route: str, intent: str) -> str:
    if intent in DATA_QUERY_INTENTS:
        return "FOLLOW_UP_MODIFY_QUERY" if route == "FOLLOW_UP_MODIFY_QUERY" else "DATA_QUERY"
    if intent == "UNSUPPORTED":
        return "DATA_QUERY"
    if intent == "OFF_TOPIC":
        return "OFF_TOPIC"
    if intent == "DIRECT_ANSWER":
        return "DIRECT_ANSWER"
    if intent == "GENERAL_EXPLANATION":
        return "GENERAL_EXPLANATION"
    if intent == "NEED_CLARIFICATION":
        return "NEED_CLARIFICATION"
    return route if route in ALLOWED_ROUTES else "DATA_QUERY"


def _validate_years(
    start_year: int | None,
    end_year: int | None,
) -> tuple[int | None, int | None, int | None, int | None, list[str], str | None]:
    warnings: list[str] = []
    effective_start_year = start_year
    effective_end_year = end_year

    if effective_end_year is not None and effective_end_year > 2025:
        effective_end_year = 2025
        warnings.append("Dữ liệu hiện chỉ được xác minh đến năm 2025, hệ thống dùng năm 2025 làm mốc cuối.")

    if effective_start_year is not None and effective_start_year < 1980:
        effective_start_year = 1980
        warnings.append("Dữ liệu hiện được xác minh từ năm 1980, hệ thống dùng năm 1980 làm mốc đầu.")

    if start_year is not None and start_year > 2025:
        return start_year, end_year, effective_start_year, effective_end_year, warnings, "Khoảng thời gian yêu cầu nằm ngoài dữ liệu hiện có."

    if end_year is not None and end_year < 1980:
        return start_year, end_year, effective_start_year, effective_end_year, warnings, "Khoảng thời gian yêu cầu nằm ngoài dữ liệu hiện có."

    return start_year, end_year, effective_start_year, effective_end_year, warnings, None


def _clamp(value: int, min_value: int, max_value: int) -> int:
    return max(min_value, min(max_value, int(value)))


def _normalize_country_groups(raw_groups: list[Any]) -> tuple[list[str], list[str]]:
    valid: list[str] = []
    invalid: list[str] = []

    for value in raw_groups or []:
        code = str(value or "").upper().strip()
        if not code:
            continue
        if get_country_group(code):
            if code not in valid:
                valid.append(code)
        elif code not in invalid:
            invalid.append(code)

    return valid, invalid


def _normalize_country_codes(raw_countries: list[Any]) -> tuple[list[str], list[str]]:
    normalized_codes = [str(value or "").upper().strip() for value in raw_countries]

    valid: list[str] = []
    invalid: list[str] = []

    for code in normalized_codes:
        if not code:
            continue
        if code in COUNTRIES:
            if code not in valid:
                valid.append(code)
        elif code not in invalid:
            invalid.append(code)

    return valid, invalid


def _dedupe(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return result


def _append_unique(items: list[str], value: str) -> None:
    text = str(value or "").strip()
    if text and text not in items:
        items.append(text)
