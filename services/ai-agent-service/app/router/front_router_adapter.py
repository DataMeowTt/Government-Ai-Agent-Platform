from typing import Any

from app.pipeline.schemas import FrontRouterDraft, RuleRouteDraft


def build_front_router_draft_from_existing_router(
    router_result: dict[str, Any] | None,
    rule_draft: RuleRouteDraft | None = None,
) -> FrontRouterDraft:
    data = router_result if isinstance(router_result, dict) else {}

    if data:
        route = _optional_str(data.get("route"))
        clarification_question = _optional_str(data.get("clarification_question"))
        clarification_questions = _string_list(data.get("clarification_questions"))
        if clarification_question and clarification_question not in clarification_questions:
            clarification_questions.insert(0, clarification_question)
        default_needs_parser = route in {None, "DATA_QUERY", "FOLLOW_UP_MODIFY_QUERY"}
        default_needs_db = route in {None, "DATA_QUERY", "FOLLOW_UP_MODIFY_QUERY"}

        return FrontRouterDraft(
            route=route,
            answer=_optional_str(data.get("answer")),
            rewritten_query=_optional_str(data.get("rewritten_query")),
            needs_parser=_bool_or_default(data.get("needs_parser"), default_needs_parser),
            needs_db=_bool_or_default(data.get("needs_db"), default_needs_db),
            clarification_question=clarification_question,
            clarification_questions=clarification_questions,
            uses_previous_context=bool(data.get("uses_previous_context") or data.get("uses_previous_result")),
            confidence=_float_or_zero(data.get("confidence")),
            reason=_optional_str(data.get("reason")) or "",
        )

    if rule_draft is None:
        return FrontRouterDraft(reason="No existing router result.")

    return FrontRouterDraft(
        route=rule_draft.route,
        intent_hint=rule_draft.intent_hint,
        needs_parser=rule_draft.needs_parser_agent,
        needs_db=rule_draft.needs_db,
        clarification_question=rule_draft.clarification_questions[0] if rule_draft.clarification_questions else None,
        draft_indicators=list(rule_draft.draft_indicators),
        draft_countries=list(rule_draft.draft_countries),
        draft_country_groups=list(rule_draft.draft_country_groups),
        draft_start_year=rule_draft.draft_start_year,
        draft_end_year=rule_draft.draft_end_year,
        draft_limit=rule_draft.draft_limit,
        draft_ranking_order=rule_draft.draft_ranking_order,
        unsupported_terms=[],
        clarification_questions=list(rule_draft.clarification_questions),
        uses_previous_context=rule_draft.uses_previous_context,
        confidence=rule_draft.confidence,
        reason=rule_draft.reason,
    )


def _string_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, tuple):
        return [str(item) for item in value if item]
    return [str(value)]


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_zero(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _bool_or_default(value: Any, default: bool) -> bool:
    if value is None:
        return default
    return bool(value)
