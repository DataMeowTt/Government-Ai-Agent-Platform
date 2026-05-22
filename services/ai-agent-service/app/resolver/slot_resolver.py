from dataclasses import dataclass

from app.resolver.country_resolver import country_match_to_dict, resolve_countries
from app.resolver.indicator_resolver import indicator_match_to_dict, resolve_indicators
from app.resolver.year_resolver import resolve_year_range


@dataclass(frozen=True)
class ResolvedSlots:
    indicators: list[dict]
    countries: list[dict]
    start_year: int | None
    end_year: int | None
    years: list[int]
    needs_clarification: bool
    clarification_questions: list[str]


def resolve_slots(message: str) -> ResolvedSlots:
    indicator_matches = resolve_indicators(message)
    country_matches = resolve_countries(message)
    year_range = resolve_year_range(message)

    indicators = [indicator_match_to_dict(match) for match in indicator_matches]
    countries = [country_match_to_dict(match) for match in country_matches]

    clarification_questions: list[str] = []

    if not indicators:
        clarification_questions.append(
            "Bạn muốn phân tích chỉ số nào? Ví dụ: nợ công, thất nghiệp, lạm phát CPI, tăng trưởng GDP thực..."
        )

    needs_clarification = len(clarification_questions) > 0

    return ResolvedSlots(
        indicators=indicators,
        countries=countries,
        start_year=year_range.start_year,
        end_year=year_range.end_year,
        years=year_range.years or [],
        needs_clarification=needs_clarification,
        clarification_questions=clarification_questions,
    )

def resolved_slots_to_metadata(slots: ResolvedSlots) -> dict:
    analytics_indicators = [
        item["code"]
        for item in slots.indicators
        if item.get("analytics", {}).get("has_analytics")
    ]

    raw_only_indicators = [
        item["code"]
        for item in slots.indicators
        if not item.get("analytics", {}).get("has_analytics")
    ]

    return {
        "indicators": [item["code"] for item in slots.indicators],
        "analytics_indicators": analytics_indicators,
        "raw_only_indicators": raw_only_indicators,
        "countries": [item["code"] for item in slots.countries],
        "years": slots.years,
        "resolved": {
            "indicators": slots.indicators,
            "countries": slots.countries,
            "start_year": slots.start_year,
            "end_year": slots.end_year,
            "needs_clarification": slots.needs_clarification,
            "clarification_questions": slots.clarification_questions,
        },
    }