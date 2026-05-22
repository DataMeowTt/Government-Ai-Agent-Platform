import re
from typing import Any

from app.catalog.canonical_indicator_catalog import (
    is_supported_indicator,
    normalize_catalog_text,
    resolve_indicator_alias,
)
from app.catalog.country_group_catalog import get_country_group, resolve_country_groups
from app.pipeline.schemas import FrontRouterDraft, ParsedQueryCandidate, RuleRouteDraft
from app.resolver.country_resolver import COUNTRIES, resolve_countries


SUPPORTED_ALIAS_OVERRIDES = {
    "trade open pct gdp": "trade_pct_gdp",
    "trade openness": "trade_pct_gdp",
    "trade pct gdp": "trade_pct_gdp",
    "trade to gdp": "trade_pct_gdp",
    "trade-to-gdp": "trade_pct_gdp",
    "do mo thuong mai": "trade_pct_gdp",
    "thuong mai/gdp": "trade_pct_gdp",
    "thuong mai tren gdp": "trade_pct_gdp",
    "gdp pc": "log_rGDP_pc_USD",
    "gdp per capita": "log_rGDP_pc_USD",
    "real gdp per capita": "log_rGDP_pc_USD",
    "gdp binh quan dau nguoi": "log_rGDP_pc_USD",
    "thu nhap binh quan": "log_rGDP_pc_USD",
    "public debt": "govdebt_GDP",
    "government debt": "govdebt_GDP",
    "debt to gdp": "govdebt_GDP",
    "debt/gdp": "govdebt_GDP",
    "no cong/gdp": "govdebt_GDP",
    "no cong": "govdebt_GDP",
    "unemployment": "unemployment_total",
    "that nghiep": "unemployment_total",
    "poverty headcount": "poverty_headcount",
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
    "GENERAL_EXPLANATION",
}


def normalize_parser_output(
    *,
    parsed: dict | None,
    standalone_query: str,
    route: str,
    front_draft: FrontRouterDraft | None,
    rule_draft: RuleRouteDraft | None,
) -> ParsedQueryCandidate:
    safe_parsed = parsed if isinstance(parsed, dict) else {}
    normalized_query = normalize_catalog_text(standalone_query)
    notes: list[str] = []

    model_indicators, model_unsupported = _normalize_model_indicators(safe_parsed)
    indicators = list(model_indicators)
    unsupported_terms = list(model_unsupported)

    resolver_match = resolve_indicator_alias(standalone_query)
    if resolver_match:
        _append_unique(indicators, resolver_match.indicator.code)
        notes.append(f"indicator resolved from standalone query: {resolver_match.indicator.code}")

    query_override = _indicator_override(normalized_query)
    if query_override:
        _append_unique(indicators, query_override)
        notes.append(f"indicator alias normalized to {query_override}")

    if not indicators and rule_draft and len(rule_draft.draft_indicators) == 1:
        indicator_code = rule_draft.draft_indicators[0]
        if is_supported_indicator(indicator_code):
            _append_unique(indicators, indicator_code)
            notes.append(f"indicator filled from rule draft: {indicator_code}")

    countries = _normalize_model_countries(safe_parsed, standalone_query)
    for match in resolve_countries(standalone_query):
        _append_unique(countries, match.country.code)
    if not countries and rule_draft and rule_draft.draft_countries:
        for code in rule_draft.draft_countries:
            if _is_country_code(code):
                _append_unique(countries, str(code).upper())
        if countries:
            notes.append("countries filled from rule draft")

    country_groups = _normalize_country_groups([
        *_string_list(safe_parsed.get("country_groups")),
        *_string_list(safe_parsed.get("country_group")),
    ])
    for match in resolve_country_groups(standalone_query):
        _append_unique(country_groups, match.group.code)
    if not country_groups and rule_draft and rule_draft.draft_country_groups:
        for code in rule_draft.draft_country_groups:
            if get_country_group(str(code)):
                _append_unique(country_groups, str(code).upper())
        if country_groups:
            notes.append("country groups filled from rule draft")

    intent = _normalize_intent(safe_parsed.get("intent"))
    if not intent and rule_draft and rule_draft.intent_hint:
        intent = _normalize_intent(rule_draft.intent_hint)
    if not intent:
        intent = _infer_intent(normalized_query, indicators, countries, country_groups)

    if route == "GENERAL_EXPLANATION":
        intent = "GENERAL_EXPLANATION"
    if _front_route(front_draft) in {"OFF_TOPIC", "NEED_CLARIFICATION", "FOLLOW_UP_ANALYSIS", "UNSUPPORTED"}:
        intent = str(_front_route(front_draft))
    elif unsupported_terms:
        intent = "UNSUPPORTED"

    start_year, end_year = _normalize_years(safe_parsed, normalized_query, intent)
    if start_year is None and rule_draft and rule_draft.draft_start_year is not None:
        start_year = rule_draft.draft_start_year
    if end_year is None and rule_draft and rule_draft.draft_end_year is not None:
        end_year = rule_draft.draft_end_year

    limit = _clamp_limit(_first_value(safe_parsed.get("limit"), _extract_limit(normalized_query)))
    if limit is None and rule_draft and rule_draft.draft_limit is not None:
        limit = _clamp_limit(rule_draft.draft_limit)

    ranking_order = _normalize_order(
        _first_value(
            safe_parsed.get("ranking_order"),
            safe_parsed.get("order"),
            _extract_order(normalized_query),
            rule_draft.draft_ranking_order if rule_draft else None,
        )
    )

    if intent == "RANKING" and start_year is None and end_year is not None:
        start_year = end_year
    elif intent == "RANKING" and start_year is not None and end_year is None:
        end_year = start_year

    route_value = _choose_route(route, front_draft, rule_draft)
    if route_value == "FOLLOW_UP_MODIFY_QUERY":
        route_value = "DATA_QUERY"
    if intent == "UNSUPPORTED":
        route_value = "DATA_QUERY"

    confidence = max(
        _float(safe_parsed.get("confidence")),
        front_draft.confidence if front_draft else 0.0,
        rule_draft.confidence if rule_draft else 0.0,
        0.85 if indicators else 0.55,
    )

    return ParsedQueryCandidate(
        route=route_value,
        intent=intent,
        indicators=_dedupe(indicators),
        countries=_dedupe(countries),
        country_groups=_dedupe(country_groups),
        start_year=start_year,
        end_year=end_year,
        limit=limit,
        ranking_order=ranking_order,
        unsupported_terms=_dedupe(unsupported_terms),
        clarification_questions=_dedupe(_string_list(safe_parsed.get("clarification_questions"))),
        source="normalization_guard",
        confidence=min(confidence, 1.0),
        reason="Normalized parser model output with deterministic catalog and standalone-query resolvers.",
        normalization_notes=notes,
        candidate_sources={
            "parser_model": bool(safe_parsed),
            "resolver": bool(resolver_match or countries or country_groups),
            "rule_draft": rule_draft is not None,
            "front_draft": front_draft is not None,
        },
    )


def _front_route(front_draft: FrontRouterDraft | None) -> str | None:
    route = front_draft.route if front_draft else None
    return str(route).upper().strip() if route else None


def _rule_route(rule_draft: RuleRouteDraft | None) -> str | None:
    route = rule_draft.route if rule_draft else None
    return str(route).upper().strip() if route else None


def _choose_route(
    route: str | None,
    front_draft: FrontRouterDraft | None,
    rule_draft: RuleRouteDraft | None,
) -> str:
    front_route = _front_route(front_draft)
    rule_route = _rule_route(rule_draft)
    route_hint = str(route or "").upper().strip() or None

    if front_route in {"OFF_TOPIC", "NEED_CLARIFICATION", "FOLLOW_UP_ANALYSIS", "UNSUPPORTED", "GENERAL_EXPLANATION"}:
        return front_route
    if front_route in {"DATA_QUERY", "FOLLOW_UP_MODIFY_QUERY"}:
        return front_route
    if rule_route == "FOLLOW_UP_MODIFY_QUERY":
        return rule_route
    if rule_route in {"OFF_TOPIC", "NEED_CLARIFICATION", "FOLLOW_UP_ANALYSIS", "UNSUPPORTED"}:
        return "DATA_QUERY"
    if route_hint in {"OFF_TOPIC", "NEED_CLARIFICATION", "FOLLOW_UP_ANALYSIS", "UNSUPPORTED", "GENERAL_EXPLANATION"}:
        return route_hint
    return route_hint or rule_route or "DATA_QUERY"


def _normalize_model_indicators(parsed: dict[str, Any]) -> tuple[list[str], list[str]]:
    indicators: list[str] = []

    raw_values = [
        *_string_list(parsed.get("indicators")),
        *_string_list(parsed.get("indicator")),
    ]

    for raw in raw_values:
        indicator_code = _normalize_indicator_text(raw)
        if indicator_code:
            _append_unique(indicators, indicator_code)
            continue

    return indicators, []


def _normalize_indicator_text(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if is_supported_indicator(text):
        return text

    normalized = normalize_catalog_text(text)
    override = SUPPORTED_ALIAS_OVERRIDES.get(normalized)
    if override and is_supported_indicator(override):
        return override

    alias_match = resolve_indicator_alias(text)
    if alias_match and is_supported_indicator(alias_match.indicator.code):
        return alias_match.indicator.code

    return None


def _indicator_override(normalized_query: str) -> str | None:
    best_code = None
    best_length = 0
    padded = f" {normalized_query} "
    for alias, code in SUPPORTED_ALIAS_OVERRIDES.items():
        alias_norm = normalize_catalog_text(alias)
        if f" {alias_norm} " in padded or alias_norm in normalized_query:
            if len(alias_norm) > best_length and is_supported_indicator(code):
                best_code = code
                best_length = len(alias_norm)
    return best_code


def _normalize_model_countries(parsed: dict[str, Any], standalone_query: str) -> list[str]:
    raw_codes = _string_list(parsed.get("countries") or parsed.get("country_codes"))
    normalized_query = normalize_catalog_text(standalone_query)
    mentions_vietnam = "vietnam" in normalized_query or "viet nam" in normalized_query
    mentions_namibia = "namibia" in normalized_query

    countries: list[str] = []
    for raw in raw_codes:
        code = str(raw or "").upper().strip()
        if code == "NAM" and mentions_vietnam and not mentions_namibia:
            continue
        if _is_country_code(code):
            _append_unique(countries, code)
            continue
        for match in resolve_countries(str(raw)):
            _append_unique(countries, match.country.code)
    return countries


def _normalize_country_groups(raw_groups: list[str]) -> list[str]:
    groups: list[str] = []
    for raw in raw_groups:
        code = str(raw or "").upper().strip()
        if get_country_group(code):
            _append_unique(groups, code)
            continue
        for match in resolve_country_groups(str(raw)):
            _append_unique(groups, match.group.code)
    return groups


def _normalize_years(parsed: dict[str, Any], normalized_query: str, intent: str) -> tuple[int | None, int | None]:
    start_year = _int_or_none(_first_value(parsed.get("start_year"), parsed.get("from_year")))
    end_year = _int_or_none(_first_value(parsed.get("end_year"), parsed.get("to_year"), parsed.get("year")))
    years = [int(year) for year in re.findall(r"\b((?:19|20)\d{2})\b", normalized_query)]

    if start_year is None and years:
        start_year = years[0]
    if end_year is None and years:
        end_year = years[-1]

    if len(years) == 1 and intent in {"RANKING", "VALUE_LOOKUP"}:
        start_year = end_year = years[0]

    return start_year, end_year


def _normalize_intent(value: Any) -> str | None:
    text = str(value or "").upper().strip()
    if not text:
        return None
    if text == "DIRECT_ANSWER":
        return "GENERAL_EXPLANATION"
    return text if text in ALLOWED_INTENTS else None


def _infer_intent(
    normalized_query: str,
    indicators: list[str],
    countries: list[str],
    country_groups: list[str],
) -> str:
    if any(token in normalized_query for token in ("coverage", "pham vi du lieu", "du lieu co tu", "co du lieu khong")):
        return "COVERAGE"
    if any(token in normalized_query for token in ("top", "xep hang", "cao nhat", "thap nhat", "highest", "lowest")):
        return "RANKING"
    if any(token in normalized_query for token in ("so sanh", "compare", " vs ", "voi", "giua")) and (
        len(countries) >= 2 or country_groups
    ):
        return "COMPARE_COUNTRIES"
    if any(token in normalized_query for token in ("bat thuong", "anomaly", "outlier")):
        return "ANOMALY_DETECTION"
    if any(token in normalized_query for token in ("xu huong", "trend", "qua cac nam", "theo thoi gian")):
        return "TREND_ANALYSIS"
    if indicators and (countries or country_groups):
        return "TIME_SERIES"
    if indicators:
        return "VALUE_LOOKUP"
    return "NEED_CLARIFICATION"


def _extract_limit(normalized_query: str) -> int | None:
    match = re.search(r"\btop\s+(\d+)\b", normalized_query)
    return int(match.group(1)) if match else None


def _extract_order(normalized_query: str) -> str | None:
    if any(token in normalized_query for token in ("thap nhat", "lowest", "nho nhat")):
        return "asc"
    if any(token in normalized_query for token in ("cao nhat", "highest", "lon nhat", "top")):
        return "desc"
    return None


def _normalize_order(value: Any) -> str | None:
    text = str(value or "").lower().strip()
    if text in {"asc", "ascending"}:
        return "asc"
    if text in {"desc", "descending"}:
        return "desc"
    return None


def _clamp_limit(value: Any) -> int | None:
    number = _int_or_none(value)
    if number is None:
        return None
    return max(1, min(number, 50))


def _first_value(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _string_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item or "").strip()]
    return [str(value)]


def _is_country_code(value: Any) -> bool:
    return str(value or "").upper().strip() in COUNTRIES


def _append_unique(items: list[str], value: str) -> None:
    text = str(value or "").strip()
    if text and text not in items:
        items.append(text)


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        _append_unique(result, value)
    return result
