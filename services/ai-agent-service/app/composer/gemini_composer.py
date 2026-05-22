import json
from typing import Any

from app.core.config import settings
from app.llm.gemini_client import GeminiClientError, generate_gemini_text, is_gemini_enabled


MAX_ROWS_FOR_GEMINI = 80


def _safe_json(data: Any) -> str:
    return json.dumps(
        data,
        ensure_ascii=False,
        indent=2,
        default=str,
    )


def _truncate_rows(rows: list[dict], max_rows: int = MAX_ROWS_FOR_GEMINI) -> list[dict]:
    if len(rows) <= max_rows:
        return rows

    return rows[:max_rows]


def should_use_gemini(question_type: str, row_count: int, user_message: str = "") -> bool:
    if not settings.gemini_composer_enabled or not is_gemini_enabled():
        return False

    numeric_data_question_types = {
        "VALID_COMPARE_QUERY",
        "VALID_RANKING_QUERY",
        "VALID_COVERAGE_QUERY",
        "VALID_TREND_QUERY",
        "VALID_ANOMALY_QUERY",
        "VALID_SIMPLE_QUERY",
    }

    if question_type in numeric_data_question_types:
        return bool(settings.enable_gemini_numeric_composer and row_count > 0)

    if question_type in {
        "OFF_TOPIC",
        "NEED_CLARIFICATION",
        "UNSUPPORTED_DATA_QUERY",
        "UNSUPPORTED",
    }:
        return False

    if row_count <= 0:
        return False

    normalized_message = user_message.lower()
    analysis_keywords = (
        "phân tích",
        "phan tich",
        "giải thích",
        "giai thich",
        "nhận xét",
        "nhan xet",
        "insight",
        "why",
        "analyze",
    )
    return any(keyword in normalized_message for keyword in analysis_keywords)


def compose_gemini_answer(
    user_message: str,
    question_type: str,
    indicator_code: str | None,
    result_payload: dict[str, Any],
    template_answer: str,
) -> str:
    rows = result_payload.get("rows", [])

    if isinstance(rows, list):
        rows_for_prompt = _truncate_rows(rows)
    else:
        rows_for_prompt = rows

    prompt_payload = {
        "user_message": user_message,
        "question_type": question_type,
        "indicator_code": indicator_code,
        "template_answer": template_answer,
        "result": {
            **result_payload,
            "rows": rows_for_prompt,
        },
    }

    prompt = f"""
Bạn là trợ lý phân tích dữ liệu kinh tế - xã hội.

Nhiệm vụ:
- Viết câu trả lời bằng tiếng Việt.
- Dựa CHỈ trên dữ liệu JSON được cung cấp.
- Không bịa số liệu.
- Không tự suy đoán ngoài dữ liệu.
- Không viết SQL.
- Không lộ thuật ngữ nội bộ như Gemini Router, router, parser, parsedQuery, AI Agent, AI Agent Service, database, DB, query planner, tool, model parser, ngrok, Kaggle.
- Nếu cần nhắc nguồn, dùng "kết quả đã hiển thị" hoặc "dữ liệu được cung cấp".
- Nếu dữ liệu rỗng, nói rõ là không tìm thấy dữ liệu phù hợp.
- Trả lời ngắn gọn, có insight chính, không quá dài.

Dữ liệu đầu vào:
{_safe_json(prompt_payload)}

Hãy viết câu trả lời cuối cho người dùng.
""".strip()

    try:
        return generate_gemini_text(prompt)
    except GeminiClientError:
        return template_answer
