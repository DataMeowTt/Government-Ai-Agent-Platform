import json
from typing import Any

from app.llm.gemini_client import GeminiClientError, generate_gemini_text


def compose_followup_analysis_answer(
    user_message: str,
    router_context: dict[str, Any],
    fallback_answer: str | None = None,
) -> tuple[str, bool]:
    prompt_payload = {
        "user_message": user_message,
        "previous_context": router_context,
    }
    prompt = f"""
Bạn là trợ lý phân tích dữ liệu kinh tế - xã hội.

Nhiệm vụ:
- Viết tiếng Việt.
- Chỉ dựa trên previous_context được cung cấp.
- Không bịa số liệu, không thêm số ngoài JSON.
- Nếu người dùng hỏi "vì sao"/"lý do", phải nói rõ: "Đây là phân tích định tính, không phải bằng chứng nhân quả trực tiếp."
- Không lộ thuật ngữ nội bộ như Gemini Router, router, parser, parsedQuery, AI Agent, AI Agent Service, database, DB, query planner, tool, model parser, ngrok, Kaggle.
- Nếu cần nhắc nguồn, dùng "dữ liệu trước đó", "bảng kết quả trước đó" hoặc "kết quả đã hiển thị".
- Trả lời ngắn gọn, có insight chính.

Input:
{json.dumps(prompt_payload, ensure_ascii=False, indent=2, default=str)}
""".strip()

    try:
        return generate_gemini_text(prompt), True
    except GeminiClientError:
        if fallback_answer:
            return fallback_answer, False
        return (
            "Dựa trên kết quả đã hiển thị, mình chỉ có thể nhận xét ở mức định tính. "
            "Đây là phân tích định tính, không phải bằng chứng nhân quả trực tiếp.",
            False,
        )
