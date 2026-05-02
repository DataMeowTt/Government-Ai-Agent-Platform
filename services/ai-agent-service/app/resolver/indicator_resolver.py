import re
import unicodedata
from dataclasses import asdict, dataclass

from app.catalog.indicator_catalog import INDICATORS, IndicatorMeta
from app.catalog.analytics_catalog import get_indicator_analytics_metadata

@dataclass(frozen=True)
class IndicatorMatch:
    indicator: IndicatorMeta
    confidence: float
    matched_alias: str


def normalize_text(text: str) -> str:
    text = text.lower().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("_", " ")
    text = re.sub(r"[^a-z0-9%\s/.-]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _contains_alias(normalized_text: str, normalized_alias: str) -> bool:
    if not normalized_alias:
        return False

    if len(normalized_alias) <= 3:
        return re.search(rf"(^|\s){re.escape(normalized_alias)}($|\s)", normalized_text) is not None

    return normalized_alias in normalized_text


def _score_alias(normalized_text: str, alias: str) -> float:
    normalized_alias = normalize_text(alias)

    if not _contains_alias(normalized_text, normalized_alias):
        return 0.0

    if normalized_text == normalized_alias:
        return 1.0

    # Alias càng dài càng đáng tin.
    # Ví dụ "no cong" đáng tin hơn "debt".
    return min(0.99, 0.55 + len(normalized_alias) / 60)


def resolve_indicator(message: str) -> IndicatorMatch | None:
    matches = resolve_indicators(message, limit=1)
    return matches[0] if matches else None


def resolve_indicators(message: str, limit: int = 3) -> list[IndicatorMatch]:
    normalized_message = normalize_text(message)
    matches: list[IndicatorMatch] = []

    for indicator in INDICATORS.values():
        candidate_aliases = (
            indicator.code,
            indicator.name,
            *indicator.aliases,
        )

        best_score = 0.0
        best_alias = ""

        for alias in candidate_aliases:
            score = _score_alias(normalized_message, alias)

            if score > best_score:
                best_score = score
                best_alias = alias

        if best_score >= 0.6:
            matches.append(
                IndicatorMatch(
                    indicator=indicator,
                    confidence=round(best_score, 3),
                    matched_alias=best_alias,
                )
            )

    matches.sort(key=lambda item: item.confidence, reverse=True)
    return matches[:limit]


def indicator_match_to_dict(match: IndicatorMatch) -> dict:
    data = asdict(match.indicator)

    analytics_metadata = get_indicator_analytics_metadata(match.indicator.code)

    data["confidence"] = match.confidence
    data["matched_alias"] = match.matched_alias
    data["analytics"] = analytics_metadata
    if analytics_metadata["analytics_table"]:
        data["analytics_table"] = analytics_metadata["analytics_table"]

    return data