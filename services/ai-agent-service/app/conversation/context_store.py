from copy import deepcopy
from typing import Any

from app.core.config import settings


DEFAULT_CONVERSATION_ID = "__default__"
_CONVERSATIONS: dict[str, dict[str, Any]] = {}


def _key(conversation_id: str | None) -> str:
    return conversation_id or DEFAULT_CONVERSATION_ID


def _empty_context(conversation_id: str | None) -> dict[str, Any]:
    return {
        "conversation_id": _key(conversation_id),
        "recent_turns": [],
        "last_user_message": None,
        "last_answer": None,
        "last_route": None,
        "last_status": None,
        "last_question_type": None,
        "last_data_query": {},
        "last_parsed_query": {},
        "last_validated_query": {},
        "last_query_plan": {},
        "last_rows": [],
        "last_chart": {},
        "last_result_summary": {},
        "last_chart_summary": {},
        "last_general_explanation": {},
        "last_result_validation": {},
        "last_data_summary": {},
        "last_parser_debug": {},
        "turn_count": 0,
    }


def get_conversation_context(conversation_id: str | None) -> dict[str, Any]:
    key = _key(conversation_id)
    if key not in _CONVERSATIONS:
        _CONVERSATIONS[key] = _empty_context(key)
    return deepcopy(_CONVERSATIONS[key])


def update_conversation_context(
    conversation_id: str | None,
    patch: dict[str, Any],
) -> dict[str, Any]:
    key = _key(conversation_id)
    current = _CONVERSATIONS.get(key) or _empty_context(key)
    patch_copy = dict(patch or {})
    append_turns = patch_copy.pop("append_recent_turns", None)

    next_context = {**current, **patch_copy}
    if append_turns:
        next_context["recent_turns"] = append_recent_turns(
            current,
            list(append_turns),
            settings.conversation_context_max_turns,
        )
    next_context["conversation_id"] = key
    next_context["turn_count"] = int(current.get("turn_count") or 0) + 1
    _CONVERSATIONS[key] = next_context
    return deepcopy(next_context)


def summarize_rows(rows: list[dict], max_rows: int) -> dict[str, Any]:
    safe_rows = rows if isinstance(rows, list) else []
    safe_limit = max(0, max_rows)
    return {
        "row_count": len(safe_rows),
        "top_rows": deepcopy(safe_rows[:safe_limit]),
    }


def append_recent_turns(
    context: dict[str, Any],
    turns: list[dict],
    max_turns: int | None = None,
) -> list[dict]:
    max_role_entries = min(max(1, int(max_turns or settings.conversation_context_max_turns)) * 2, 20)
    current_turns = context.get("recent_turns") or []
    merged = [
        deepcopy(turn)
        for turn in [*current_turns, *(turns or [])]
        if isinstance(turn, dict) and turn.get("role")
    ]
    return merged[-max_role_entries:]


def make_user_turn(message: str) -> dict[str, Any]:
    return {
        "role": "user",
        "content": str(message or "").strip(),
    }


def make_assistant_turn(
    answer: str,
    status: str,
    question_type: str,
    route: str,
    answer_summary: str | None = None,
) -> dict[str, Any]:
    content = str(answer_summary or answer or "").strip()
    return {
        "role": "assistant",
        "content": content,
        "status": status,
        "question_type": question_type,
        "route": route,
    }


def build_router_context(context: dict[str, Any]) -> dict[str, Any]:
    last_chart = context.get("last_chart") or {}
    chart_metadata = {
        key: value
        for key, value in last_chart.items()
        if key != "data"
    }

    max_rows = settings.conversation_context_max_rows
    max_items = min(max(1, settings.conversation_context_max_turns) * 2, 20)
    last_rows = context.get("last_rows") or []
    recent_turns = context.get("recent_turns") or []

    return {
        "conversation_id": context.get("conversation_id"),
        "turn_count": context.get("turn_count", 0),
        "recent_turns": deepcopy(recent_turns[-max_items:]),
        "last_user_message": context.get("last_user_message"),
        "last_answer": context.get("last_answer"),
        "last_route": context.get("last_route"),
        "last_status": context.get("last_status"),
        "last_question_type": context.get("last_question_type"),
        "last_data_query": context.get("last_data_query") or {},
        "last_parsed_query": context.get("last_parsed_query") or {},
        "last_validated_query": context.get("last_validated_query") or {},
        "last_query_plan": context.get("last_query_plan") or {},
        "last_result_summary": context.get("last_result_summary") or {},
        "last_chart_summary": context.get("last_chart_summary") or {},
        "last_general_explanation": context.get("last_general_explanation") or {},
        "last_result_validation": context.get("last_result_validation") or {},
        "last_data_summary": context.get("last_data_summary") or {},
        "last_chart": chart_metadata,
        "last_rows": deepcopy(last_rows[:max_rows]),
    }


def build_front_llm_context(context: dict[str, Any], max_user_questions: int = 7) -> dict[str, Any]:
    """Compact, user-facing context for the front LLM router only."""
    recent_turns = context.get("recent_turns") or []
    limit = max(1, min(int(max_user_questions or 7), 7))
    questions: list[str] = []

    for turn in recent_turns:
        if not isinstance(turn, dict) or turn.get("role") != "user":
            continue
        content = _truncate_text(turn.get("content"), 240)
        if content:
            questions.append(content)

    return {
        "recent_user_questions": questions[-limit:],
    }


def _truncate_text(value: Any, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars].rstrip()}..."
