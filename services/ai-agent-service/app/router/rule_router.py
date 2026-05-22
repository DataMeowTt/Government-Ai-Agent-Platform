from typing import Literal

from app.resolver.indicator_resolver import normalize_text
from app.resolver.slot_resolver import ResolvedSlots


QuestionType = Literal[
    "OFF_TOPIC",
    "NEED_CLARIFICATION",
    "VALID_SIMPLE_QUERY",
    "VALID_COMPARE_QUERY",
    "VALID_RANKING_QUERY",
    "VALID_TREND_QUERY",
    "VALID_ANOMALY_QUERY",
    "VALID_COVERAGE_QUERY",
    "UNSUPPORTED_DATA_QUERY",
]


COMPARE_KEYWORDS = (
    "so sanh",
    "compare",
    "doi chieu",
    "vs",
    "voi",
    "giua",
)

RANKING_KEYWORDS = (
    "cao nhat",
    "thap nhat",
    "lon nhat",
    "nho nhat",
    "top",
    "xep hang",
    "ranking",
    "rank",
    "highest",
    "lowest",
    "largest",
    "smallest",
)

COVERAGE_KEYWORDS = (
    "co tu nam nao",
    "den nam nao",
    "du lieu co tu",
    "coverage",
    "data coverage",
    "co du lieu",
    "thieu du lieu",
)

ANOMALY_KEYWORDS = (
    "bat thuong",
    "di thuong",
    "anomaly",
    "outlier",
    "canh bao",
    "rui ro",
    "dot bien",
)

TREND_KEYWORDS = (
    "xu huong",
    "trend",
    "qua cac nam",
    "theo thoi gian",
    "tu nam",
    "giai doan",
)


DOMAIN_KEYWORDS = (
    "gdp",
    "no cong",
    "ngan sach",
    "lam phat",
    "that nghiep",
    "ngheo",
    "khung hoang",
    "dan so",
    "do thi",
    "dau tu",
    "thuong mai",
    "tai khoa",
    "tien te",
    "government",
    "debt",
    "inflation",
    "unemployment",
    "poverty",
    "growth",
    "crisis",
)


def _contains_any(normalized_message: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in normalized_message for keyword in keywords)


def classify_question(message: str, slots: ResolvedSlots) -> QuestionType:
    normalized_message = normalize_text(message)

    has_indicator = len(slots.indicators) > 0
    country_count = len(slots.countries)
    has_year = slots.start_year is not None or slots.end_year is not None

    if slots.needs_clarification:
        return "NEED_CLARIFICATION"

    if not has_indicator:
        if _contains_any(normalized_message, DOMAIN_KEYWORDS):
            return "NEED_CLARIFICATION"

        return "OFF_TOPIC"

    if _contains_any(normalized_message, COVERAGE_KEYWORDS):
        return "VALID_COVERAGE_QUERY"

    if _contains_any(normalized_message, ANOMALY_KEYWORDS):
        return "VALID_ANOMALY_QUERY"

    if _contains_any(normalized_message, RANKING_KEYWORDS):
        if not has_year:
            return "NEED_CLARIFICATION"

        return "VALID_RANKING_QUERY"

    if _contains_any(normalized_message, COMPARE_KEYWORDS) or country_count >= 2:
        return "VALID_COMPARE_QUERY"

    if country_count == 1:
        return "VALID_TREND_QUERY"

    if has_year:
        return "VALID_RANKING_QUERY"

    return "NEED_CLARIFICATION"