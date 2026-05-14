import re
from typing import Any

from app.catalog.canonical_indicator_catalog import (
    is_supported_indicator,
    normalize_catalog_text,
    resolve_indicator_alias,
)
from app.catalog.country_group_catalog import resolve_country_groups
from app.pipeline.schemas import FrontRouterDraft, ParsedQueryCandidate, RuleRouteDraft
from app.resolver.country_resolver import resolve_countries


def run_parser_agent(
    user_message: str,
    conversation_context: dict[str, Any] | None,
    rule_draft: RuleRouteDraft | None,
    front_draft: FrontRouterDraft | None,
    model_parsed: dict[str, Any] | None = None,
) -> ParsedQueryCandidate:
    normalized = normalize_catalog_text(user_message)
    model_indicators, model_unsupported_terms = (
        _normalize_model_indicators(model_parsed)
        if isinstance(model_parsed, dict)
        else ([], [])
    )
    indicators = _dedupe(
        [
            *(rule_draft.draft_indicators if rule_draft else []),
            *(front_draft.draft_indicators if front_draft else []),
            *model_indicators,
        ]
    )
    resolver_match = resolve_indicator_alias(user_message)
    if resolver_match and resolver_match.indicator.code not in indicators:
        indicators.append(resolver_match.indicator.code)

    unsupported_terms = _dedupe(
        [
            *(rule_draft.unsupported_terms if rule_draft else []),
            *(front_draft.unsupported_terms if front_draft else []),
            *model_unsupported_terms,
        ]
    )

    country_groups = _dedupe(
        [
            *(rule_draft.draft_country_groups if rule_draft else []),
            *(front_draft.draft_country_groups if front_draft else []),
            *[match.group.code for match in resolve_country_groups(user_message)],
            *(_string_list(model_parsed.get("country_groups")) if isinstance(model_parsed, dict) else []),
        ]
    )
    countries = _dedupe(
        [
            *(rule_draft.draft_countries if rule_draft else []),
            *(front_draft.draft_countries if front_draft else []),
            *[match.country.code for match in resolve_countries(user_message)],
            *(_normalize_model_countries(model_parsed, user_message) if isinstance(model_parsed, dict) else []),        ]
    )

    start_year, end_year = _extract_year_range(user_message, rule_draft, front_draft, model_parsed)
    limit = _first_int(
        rule_draft.draft_limit if rule_draft else None,
        front_draft.draft_limit if front_draft else None,
        _extract_limit(normalized),
        model_parsed.get("limit") if isinstance(model_parsed, dict) else None,
    )
    ranking_order = (
        (rule_draft.draft_ranking_order if rule_draft else None)
        or (front_draft.draft_ranking_order if front_draft else None)
        or _extract_order(normalized)
        or (model_parsed.get("ranking_order") if isinstance(model_parsed, dict) else None)
    )

    intent = _infer_intent(
        normalized=normalized,
        indicators=indicators,
        countries=countries,
        country_groups=country_groups,
        unsupported_terms=unsupported_terms,
        rule_draft=rule_draft,
        front_draft=front_draft,
        model_parsed=model_parsed,
    )
    route = _choose_route(rule_draft, front_draft)

    clarification_questions = _dedupe(
        [
            *(rule_draft.clarification_questions if rule_draft else []),
            *(front_draft.clarification_questions if front_draft else []),
            *(_string_list(model_parsed.get("clarification_questions")) if isinstance(model_parsed, dict) else []),
        ]
    )
    if intent != "NEED_CLARIFICATION":
        clarification_questions = []

    return ParsedQueryCandidate(
        route=route,
        intent=intent,
        indicators=indicators,
        countries=countries,
        country_groups=country_groups,
        start_year=start_year,
        end_year=end_year,
        limit=limit,
        ranking_order=ranking_order if ranking_order in {"asc", "desc"} else None,
        unsupported_terms=unsupported_terms,
        clarification_questions=clarification_questions,
        source="parser_agent",
        confidence=max(
            rule_draft.confidence if rule_draft else 0.0,
            front_draft.confidence if front_draft else 0.0,
            0.85 if indicators or unsupported_terms else 0.5,
        ),
        reason="Reconciled rule/front/model parser outputs with canonical catalog.",
        candidate_sources={
            "rule_draft": rule_draft is not None,
            "front_draft": front_draft is not None,
            "resolver": resolver_match is not None,
            "model_parser": isinstance(model_parsed, dict),
        },
    )

def _choose_route(
    rule_draft: RuleRouteDraft | None,
    front_draft: FrontRouterDraft | None,
) -> str:
    rule_route = rule_draft.route if rule_draft else None
    front_route = front_draft.route if front_draft else None

    if front_route in {"FOLLOW_UP_ANALYSIS", "NEED_CLARIFICATION", "UNSUPPORTED", "OFF_TOPIC", "GENERAL_EXPLANATION"}:
        return front_route

    if front_route in {"DATA_QUERY", "FOLLOW_UP_MODIFY_QUERY"}:
        return front_route

    if rule_route == "FOLLOW_UP_MODIFY_QUERY":
        return rule_route

    if rule_route in {"FOLLOW_UP_ANALYSIS", "UNSUPPORTED", "OFF_TOPIC", "NEED_CLARIFICATION"}:
        return "DATA_QUERY"

    return rule_route or front_route or "DATA_QUERY"

def _normalize_model_countries(model_parsed: dict[str, Any], user_message: str) -> list[str]:
    raw_codes = _string_list(model_parsed.get("countries"))
    normalized_message = normalize_catalog_text(user_message)

    result: list[str] = []
    mentions_vietnam = "vietnam" in normalized_message or "viet nam" in normalized_message
    mentions_namibia = "namibia" in normalized_message

    for raw in raw_codes:
        code = str(raw or "").upper().strip()
        if not code:
            continue

        if code == "NAM" and mentions_vietnam and not mentions_namibia:
            continue

        if code not in result:
            result.append(code)

    return result

def _infer_intent(
    normalized: str,
    indicators: list[str],
    countries: list[str],
    country_groups: list[str],
    unsupported_terms: list[str],
    rule_draft: RuleRouteDraft | None,
    front_draft: FrontRouterDraft | None,
    model_parsed: dict[str, Any] | None,
) -> str:
    if front_draft and front_draft.route in {"OFF_TOPIC", "NEED_CLARIFICATION", "FOLLOW_UP_ANALYSIS", "GENERAL_EXPLANATION"}:
        return front_draft.route

    if unsupported_terms:
        return "UNSUPPORTED"

    if front_draft and front_draft.route == "UNSUPPORTED":
        return "UNSUPPORTED"
    for intent in (
        rule_draft.intent_hint if rule_draft else None,
        front_draft.intent_hint if front_draft else None,
    ):
        if intent:
            return intent

    model_intent = str(model_parsed.get("intent") or "") if isinstance(model_parsed, dict) else ""
    if model_intent and model_intent != "NEED_CLARIFICATION":
        return model_intent

    if any(token in normalized for token in ("coverage", "pham vi du lieu", "du lieu co tu")):
        return "COVERAGE"
    if any(token in normalized for token in ("top", "xep hang", "cao nhat", "thap nhat", "highest", "lowest")):
        return "RANKING"
    if any(token in normalized for token in ("so sanh", "compare", " vs ", "voi", "giua")) and (len(countries) >= 2 or country_groups):
        return "COMPARE_COUNTRIES"
    if any(token in normalized for token in ("bat thuong", "anomaly", "outlier")):
        return "ANOMALY_DETECTION"
    if any(token in normalized for token in ("xu huong", "trend", "qua cac nam", "theo thoi gian")):
        return "TREND_ANALYSIS"
    if indicators and countries:
        return "TIME_SERIES"
    if not indicators:
        return "NEED_CLARIFICATION"
    return "VALUE_LOOKUP"


def _normalize_model_indicators(model_parsed: dict[str, Any]) -> tuple[list[str], list[str]]:
    indicators: list[str] = []

    for raw in _string_list(model_parsed.get("indicators")):
        text = str(raw).strip()
        if not text:
            continue

        if is_supported_indicator(text):
            indicators.append(text)
            continue

        alias_match = resolve_indicator_alias(text)
        if alias_match and is_supported_indicator(alias_match.indicator.code):
            indicators.append(alias_match.indicator.code)
            continue

    return _dedupe(indicators), []


def _extract_year_range(
    user_message: str,
    rule_draft: RuleRouteDraft | None,
    front_draft: FrontRouterDraft | None,
    model_parsed: dict[str, Any] | None,
) -> tuple[int | None, int | None]:
    years = [int(year) for year in re.findall(r"\b((?:19|20)\d{2})\b", user_message)]
    start_year = _first_int(
        rule_draft.draft_start_year if rule_draft else None,
        front_draft.draft_start_year if front_draft else None,
        years[0] if years else None,
        model_parsed.get("start_year") if isinstance(model_parsed, dict) else None,
    )
    end_year = _first_int(
        rule_draft.draft_end_year if rule_draft else None,
        front_draft.draft_end_year if front_draft else None,
        years[-1] if years else None,
        model_parsed.get("end_year") if isinstance(model_parsed, dict) else None,
    )
    return start_year, end_year


def _extract_limit(normalized: str) -> int | None:
    match = re.search(r"\btop\s+(\d+)\b", normalized)
    if not match:
        return None
    return max(1, min(int(match.group(1)), 50))


def _extract_order(normalized: str) -> str | None:
    if any(token in normalized for token in ("thap nhat", "lowest", "nho nhat")):
        return "asc"
    if any(token in normalized for token in ("cao nhat", "highest", "lon nhat", "top")):
        return "desc"
    return None


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return result


def _string_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item]
    return [str(value)]


def _first_int(*values: Any) -> int | None:
    for value in values:
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _first_text(*values: Any) -> str:
    for value in values:
        if value:
            return str(value)
    return ""
