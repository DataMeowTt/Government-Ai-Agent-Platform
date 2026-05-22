from __future__ import annotations

from typing import Any

from app.catalog.canonical_indicator_catalog import is_supported_indicator


FORBIDDEN_PARSER_INDICATORS: frozenset[str] = frozenset(
    {"decade", "flag_score", "completeness_score"}
)


def extract_indicator_codes(parsed_query: dict[str, Any] | None) -> list[str]:
    if not isinstance(parsed_query, dict):
        return []

    values: list[str] = []
    raw_indicators = parsed_query.get("indicators")
    if isinstance(raw_indicators, list):
        values.extend(str(item).strip() for item in raw_indicators if str(item).strip())

    raw_indicator = parsed_query.get("indicator")
    if isinstance(raw_indicator, str) and raw_indicator.strip():
        values.append(raw_indicator.strip())

    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped


def validate_indicator_codes(parsed_query: dict[str, Any] | None) -> dict[str, Any]:
    codes = extract_indicator_codes(parsed_query)
    if not codes:
        return {
            "valid": True,
            "codes": [],
            "forbidden_indicators": [],
            "unknown_indicators": [],
        }

    forbidden = sorted(code for code in codes if code in FORBIDDEN_PARSER_INDICATORS)
    unknown = sorted(
        code
        for code in codes
        if code not in FORBIDDEN_PARSER_INDICATORS and not is_supported_indicator(code)
    )

    return {
        "valid": not (forbidden or unknown),
        "codes": codes,
        "forbidden_indicators": forbidden,
        "unknown_indicators": unknown,
    }
