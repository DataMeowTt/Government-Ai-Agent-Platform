import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class CountryGroup:
    code: str
    name_vi: str
    name_en: str
    aliases: tuple[str, ...]
    countries: tuple[str, ...]


@dataclass(frozen=True)
class CountryGroupMatch:
    group: CountryGroup
    matched_alias: str
    confidence: float


COUNTRY_GROUPS: dict[str, CountryGroup] = {
    "ASEAN": CountryGroup(
        code="ASEAN",
        name_vi="ASEAN",
        name_en="Association of Southeast Asian Nations",
        aliases=(
            "ASEAN",
            "Đông Nam Á",
            "Dong Nam A",
            "Southeast Asia",
            "các nước ASEAN",
            "cac nuoc ASEAN",
        ),
        countries=(
            "VNM",
            "THA",
            "IDN",
            "MYS",
            "PHL",
            "SGP",
            "KHM",
            "LAO",
            "MMR",
            "BRN",
        ),
    ),
    "G7": CountryGroup(
        code="G7",
        name_vi="Nhóm G7",
        name_en="Group of Seven",
        aliases=(
            "G7",
            "Group of Seven",
            "nhóm G7",
            "nhom G7",
        ),
        countries=(
            "USA",
            "CAN",
            "GBR",
            "FRA",
            "DEU",
            "ITA",
            "JPN",
        ),
    ),
    "BRICS": CountryGroup(
        code="BRICS",
        name_vi="BRICS",
        name_en="BRICS",
        aliases=(
            "BRICS",
            "nhóm BRICS",
            "nhom BRICS",
        ),
        countries=(
            "BRA",
            "RUS",
            "IND",
            "CHN",
            "ZAF",
        ),
    ),
}


def normalize_group_text(text: str) -> str:
    normalized = text.lower().strip().replace("đ", "d")
    normalized = unicodedata.normalize("NFD", normalized)
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    normalized = normalized.replace("_", " ")
    normalized = re.sub(r"[^a-z0-9%\s/.-]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def get_country_group(code: str) -> CountryGroup | None:
    return COUNTRY_GROUPS.get(code.upper())


def list_country_groups() -> list[CountryGroup]:
    return list(COUNTRY_GROUPS.values())


def _contains_alias(normalized_text: str, normalized_alias: str) -> bool:
    if not normalized_alias:
        return False
    return re.search(rf"(^|\s){re.escape(normalized_alias)}($|\s)", normalized_text) is not None


def _score_alias(normalized_text: str, alias: str) -> float:
    normalized_alias = normalize_group_text(alias)
    if not _contains_alias(normalized_text, normalized_alias):
        return 0.0
    if normalized_text == normalized_alias:
        return 1.0
    return min(0.99, 0.8 + len(normalized_alias) / 300)


def resolve_country_groups(text: str) -> list[CountryGroupMatch]:
    normalized_text = normalize_group_text(text)
    matches: list[CountryGroupMatch] = []

    for group in COUNTRY_GROUPS.values():
        best_score = 0.0
        best_alias = ""
        best_alias_length = 0
        for alias in group.aliases:
            normalized_alias = normalize_group_text(alias)
            score = _score_alias(normalized_text, alias)
            alias_length = len(normalized_alias)
            if score > best_score or (score == best_score and alias_length > best_alias_length):
                best_score = score
                best_alias = alias
                best_alias_length = alias_length

        if best_score >= 0.8:
            matches.append(
                CountryGroupMatch(
                    group=group,
                    matched_alias=best_alias,
                    confidence=round(best_score, 3),
                )
            )

    matches.sort(key=lambda match: match.confidence, reverse=True)
    return matches


def resolve_country_group(text: str) -> CountryGroupMatch | None:
    matches = resolve_country_groups(text)
    return matches[0] if matches else None


def expand_country_groups(group_codes: list[str]) -> list[str]:
    countries: list[str] = []
    seen: set[str] = set()
    for group_code in group_codes:
        group = get_country_group(group_code)
        if not group:
            continue
        for country_code in group.countries:
            if country_code not in seen:
                seen.add(country_code)
                countries.append(country_code)
    return countries
