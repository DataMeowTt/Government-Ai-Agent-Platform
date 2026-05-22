from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Any

from app.catalog.canonical_indicator_catalog import resolve_indicator_alias, resolve_indicator_aliases
from app.knowledge.knowledge_corpus import KnowledgeEntry, build_knowledge_corpus
from app.resolver.country_resolver import resolve_countries


@dataclass(frozen=True)
class KnowledgeSnippet:
    id: str
    type: str
    title: str
    definition: str
    how_to_interpret: str
    example: str
    caveat: str
    score: float
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFINITION_PATTERNS = (
    "la gi",
    "dinh nghia",
    "y nghia",
    "co nghia gi",
    "giai thich",
    "cach hieu",
    "dung de",
    "phan anh",
    "cho biet dieu gi",
    "the hien dieu gi",
)
EXAMPLE_PATTERNS = ("cho vi du", "vi du ve", "example")
REASON_PATTERNS = ("vi sao", "tai sao", "nguyen nhan", "ly do", "phan tich")
SOURCE_PATTERNS = ("du lieu lay tu dau", "nguon du lieu", "du lieu nguon", "wdi", "faostat", "fao", "gmd", "world bank")
CONCEPT_PATTERNS = (
    "anomaly",
    "anomaly score",
    "bat thuong",
    "cluster",
    "cum",
    "structural cluster",
    "trend",
    "xu huong",
    "coverage",
    "missing data",
    "thieu du lieu",
)
DATA_EXECUTION_PATTERNS = (
    "so sanh",
    "xep hang",
    "top",
    "cao nhat",
    "thap nhat",
    "tu nam",
    "den nam",
    "giai doan",
    "qua cac nam",
    "theo thoi gian",
)
CONTEXT_REFERENCE_PATTERNS = (
    "nay",
    "do",
    "tren",
    "vua roi",
    "xu huong nay",
    "ket qua nay",
    "ket qua tren",
    "phan tich ki hon",
    "phan tich ky hon",
    "phan tich sau hon",
    "giai thich them",
    "nhan xet them",
)
PROVIDED_FACT_PATTERNS = (
    "gia tri la",
    "diem bat thuong thong ke la",
)


def normalize_knowledge_text(text: str) -> str:
    normalized = str(text or "").lower().strip().replace("đ", "d")
    normalized = unicodedata.normalize("NFD", normalized)
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    normalized = normalized.replace("_", " ")
    normalized = re.sub(r"[^a-z0-9%\s/.-]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def is_knowledge_question(message: str, rule_draft: Any | None = None) -> bool:
    normalized = normalize_knowledge_text(message)
    if not normalized:
        return False

    has_definition = _contains_any(normalized, DEFINITION_PATTERNS)
    has_example = _contains_any(normalized, EXAMPLE_PATTERNS)
    has_reason = _contains_any(normalized, REASON_PATTERNS)
    has_source = _contains_any(normalized, SOURCE_PATTERNS)
    has_concept = _contains_any(normalized, CONCEPT_PATTERNS)
    has_year = re.search(r"\b(?:19|20)\d{2}\b", normalized) is not None
    has_execution = _contains_any(normalized, DATA_EXECUTION_PATTERNS)
    has_context_reference = _contains_any(normalized, CONTEXT_REFERENCE_PATTERNS)
    has_provided_fact = _contains_any(normalized, PROVIDED_FACT_PATTERNS)

    countries = list(getattr(rule_draft, "draft_countries", []) or [])
    groups = list(getattr(rule_draft, "draft_country_groups", []) or [])
    resolver_countries = [match.country.code for match in resolve_countries(message)]
    resolver_indicator = resolve_indicator_alias(message)
    has_country_scope = bool(countries or groups)
    has_explicit_country = bool(countries or groups or resolver_countries)
    has_indicator_scope = bool(list(getattr(rule_draft, "draft_indicators", []) or []) or resolver_indicator)

    if has_context_reference:
        return False

    if has_provided_fact or (has_year and has_explicit_country and has_indicator_scope):
        return False

    if has_source:
        return not has_year and not has_explicit_country

    if has_definition or has_example:
        return not has_year and not has_execution

    if has_concept and not has_explicit_country and not has_year:
        return True

    if has_reason and not has_explicit_country and not has_year:
        asks_open_analysis = "phan tich" in normalized and not any(
            token in normalized for token in ("vi sao", "tai sao", "nguyen nhan", "ly do")
        )
        if asks_open_analysis and has_indicator_scope and f" {normalized} ".find(" cua ") >= 0:
            return False
        return True

    return False


def retrieve_knowledge(message: str, limit: int = 5) -> list[KnowledgeSnippet]:
    normalized = normalize_knowledge_text(message)
    if limit <= 0:
        return []

    scored: list[tuple[float, KnowledgeEntry]] = []
    indicator_matches = resolve_indicator_aliases(message, limit=3)
    indicator_codes = {match.indicator.code for match in indicator_matches}

    for entry in _corpus():
        score = _score_entry(normalized, entry, indicator_codes)
        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda item: item[0], reverse=True)
    snippets = [_to_snippet(entry, score) for score, entry in scored[:limit]]

    if snippets:
        return snippets

    return [
        _to_snippet(entry, 0.2)
        for entry in _fallback_entries()
    ][:limit]


@lru_cache(maxsize=1)
def _corpus() -> tuple[KnowledgeEntry, ...]:
    return tuple(build_knowledge_corpus())


def _score_entry(normalized: str, entry: KnowledgeEntry, indicator_codes: set[str]) -> float:
    aliases = [entry.title, *entry.aliases]
    normalized_aliases = [normalize_knowledge_text(alias) for alias in aliases if alias]
    searchable = normalize_knowledge_text(
        " ".join(
            [
                entry.id,
                entry.type,
                entry.title,
                " ".join(entry.aliases),
                entry.definition,
                entry.how_to_interpret,
                entry.example,
                entry.caveat,
            ]
        )
    )

    score = 0.0
    code = str(entry.metadata.get("code") or "")
    alias_hit = False
    if code and code in indicator_codes:
        score += 6.0

    for alias in normalized_aliases:
        if not alias:
            continue
        if normalized == alias:
            score += 5.0
            alias_hit = True
        elif _contains_phrase(normalized, alias):
            score += 3.0 + min(len(alias) / 80, 1.5)
            alias_hit = True

    overlap = _keyword_overlap(normalized, searchable)
    if entry.type == "indicator" and indicator_codes and code not in indicator_codes:
        return 0.0
    if entry.type == "indicator" and code not in indicator_codes and not alias_hit and overlap < 3:
        return 0.0
    if entry.type == "data_source" and not _contains_any(normalized, SOURCE_PATTERNS) and not alias_hit:
        return 0.0

    score += min(overlap * 0.5, 3.0)

    if entry.type == "data_source" and _contains_any(normalized, SOURCE_PATTERNS):
        score += 5.0
    if entry.type == "answer_policy" and _contains_any(normalized, REASON_PATTERNS):
        score += 2.0
    if entry.type == "system_capability" and "du lieu lay tu dau" in normalized:
        score += 1.5
    if entry.id == "concept:anomaly" and ("anomaly score" in normalized or "diem bat thuong" in normalized):
        score += 4.0
    if entry.id == "concept:cluster" and ("cluster" in normalized or " cum " in f" {normalized} "):
        score += 4.0

    return score


def _to_snippet(entry: KnowledgeEntry, score: float) -> KnowledgeSnippet:
    return KnowledgeSnippet(
        id=entry.id,
        type=entry.type,
        title=entry.title,
        definition=entry.definition,
        how_to_interpret=entry.how_to_interpret,
        example=entry.example,
        caveat=entry.caveat,
        score=round(score, 3),
        metadata=dict(entry.metadata),
    )


def _fallback_entries() -> list[KnowledgeEntry]:
    wanted = {"system:capability_scope", "policy:reasoning"}
    return [entry for entry in _corpus() if entry.id in wanted]


def _contains_any(normalized_text: str, patterns: tuple[str, ...]) -> bool:
    return any(_contains_phrase(normalized_text, pattern) for pattern in patterns)


def _contains_phrase(normalized_text: str, phrase: str) -> bool:
    normalized_phrase = normalize_knowledge_text(phrase)
    if not normalized_phrase:
        return False
    if len(normalized_phrase) <= 3:
        return re.search(rf"(^|\s){re.escape(normalized_phrase)}($|\s)", normalized_text) is not None
    if " " in normalized_phrase:
        return f" {normalized_phrase} " in f" {normalized_text} "
    return normalized_phrase in normalized_text


def _keyword_overlap(normalized_text: str, searchable: str) -> int:
    stopwords = {
        "la",
        "gi",
        "co",
        "cua",
        "ve",
        "cho",
        "toi",
        "hay",
        "mot",
        "cac",
        "du",
        "lieu",
        "phan",
        "tich",
    }
    query_tokens = {
        token
        for token in re.findall(r"[a-z0-9]{3,}", normalized_text)
        if token not in stopwords
    }
    if not query_tokens:
        return 0
    searchable_tokens = set(re.findall(r"[a-z0-9]{3,}", searchable))
    return len(query_tokens & searchable_tokens)
