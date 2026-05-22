from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RuleRouteDraft:
    matched: bool
    route: str | None = None
    confidence: float = 0.0
    needs_front_llm: bool = True
    needs_parser_agent: bool = True
    needs_db: bool = True
    uses_previous_context: bool = False
    intent_hint: str | None = None
    draft_indicators: list[str] = field(default_factory=list)
    draft_countries: list[str] = field(default_factory=list)
    draft_country_groups: list[str] = field(default_factory=list)
    draft_start_year: int | None = None
    draft_end_year: int | None = None
    draft_limit: int | None = None
    draft_ranking_order: str | None = None
    delta: dict[str, Any] | None = None
    unsupported_terms: list[str] = field(default_factory=list)
    clarification_reason: str | None = None
    clarification_questions: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass(frozen=True)
class FrontRouterDraft:
    route: str | None = None
    answer: str | None = None
    intent_hint: str | None = None
    rewritten_query: str | None = None
    needs_parser: bool = True
    needs_db: bool = True
    clarification_question: str | None = None
    draft_indicators: list[str] = field(default_factory=list)
    draft_countries: list[str] = field(default_factory=list)
    draft_country_groups: list[str] = field(default_factory=list)
    draft_start_year: int | None = None
    draft_end_year: int | None = None
    draft_limit: int | None = None
    draft_ranking_order: str | None = None
    unsupported_terms: list[str] = field(default_factory=list)
    clarification_questions: list[str] = field(default_factory=list)
    uses_previous_context: bool = False
    confidence: float = 0.0
    reason: str = ""


@dataclass(frozen=True)
class ParsedQueryCandidate:
    route: str
    intent: str
    indicators: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    country_groups: list[str] = field(default_factory=list)
    start_year: int | None = None
    end_year: int | None = None
    limit: int | None = None
    ranking_order: str | None = None
    unsupported_terms: list[str] = field(default_factory=list)
    clarification_questions: list[str] = field(default_factory=list)
    source: str = "normalization_guard"
    confidence: float = 0.0
    reason: str = ""
    normalization_notes: list[str] = field(default_factory=list)
    candidate_sources: dict[str, bool] = field(default_factory=dict)


@dataclass(frozen=True)
class ValidationOutcome:
    ok: bool
    status: str
    question_type: str
    validated_query: dict[str, Any] | None
    warnings: list[str] = field(default_factory=list)
    clarification_questions: list[str] = field(default_factory=list)
    unsupported_terms: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass(frozen=True)
class ResultValidation:
    row_count: int
    requested_countries: list[str] = field(default_factory=list)
    available_countries: list[str] = field(default_factory=list)
    missing_countries: list[str] = field(default_factory=list)
    requested_start_year: int | None = None
    requested_end_year: int | None = None
    actual_min_year: int | None = None
    actual_max_year: int | None = None
    actual_start_year: int | None = None
    actual_end_year: int | None = None
    empty_result_kind: str | None = None
    has_numeric_rows: bool = False
    is_empty: bool = False
    is_partial: bool = False
    warnings: list[str] = field(default_factory=list)
