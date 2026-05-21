from __future__ import annotations

import json
from typing import Any

from app.core.config import settings
from app.knowledge.knowledge_retriever import KnowledgeSnippet, normalize_knowledge_text
from app.llm.gemini_client import GeminiClientError, generate_gemini_text, is_gemini_enabled


def compose_knowledge_answer(message: str, snippets: list[KnowledgeSnippet]) -> tuple[str, str]:
    if settings.gemini_composer_enabled and is_gemini_enabled():
        try:
            model = settings.ai_knowledge_model or settings.ai_composer_model or settings.gemini_model
            answer = _compose_with_gemini(message, snippets, model)
            if _is_acceptable_answer(message, answer):
                return answer, "gemini"
        except GeminiClientError:
            if settings.ai_fallback_model:
                try:
                    answer = _compose_with_gemini(message, snippets, settings.ai_fallback_model)
                    if _is_acceptable_answer(message, answer):
                        return answer, "gemini"
                except GeminiClientError:
                    pass

    return _compose_template(message, snippets), "template"


def _compose_with_gemini(message: str, snippets: list[KnowledgeSnippet], model: str | None) -> str:
    prompt = f"""
Bạn là trợ lý giải thích dữ liệu kinh tế - xã hội cho dashboard phân tích chính sách.

Yêu cầu trả lời:
- Trả lời bằng tiếng Việt, giọng văn trang trọng, rõ ràng, dễ hiểu.
- Chỉ dùng KNOWLEDGE_CONTEXT và câu hỏi người dùng; không bịa số liệu.
- Không khẳng định quan hệ nhân quả chắc chắn từ dữ liệu mô tả.
- Không nhắc các thuật ngữ nội bộ như parser, BigQuery, API, route, endpoint, Cloud Run, Kaggle, ngrok, SQL, debug, secret, token.
- Không nêu đường dẫn file nội bộ.
- Có thể đưa ra các giả thuyết kinh tế hợp lý dựa trên kiến thức kinh tế phổ thông, nhưng phải ghi rõ đây là giả thuyết tham khảo và cần kiểm chứng bằng dữ liệu.
- Khi người dùng hỏi phân tích/lý do/nguyên nhân, hãy phân tích kỹ, nêu yếu tố ảnh hưởng, cơ chế tác động, dữ liệu cần kiểm tra thêm, và kết luận tham khảo.
- Nếu câu hỏi là định nghĩa, dùng cấu trúc: Định nghĩa ngắn gọn; Cách hiểu trong phân tích kinh tế; Ví dụ đơn giản; Lưu ý khi diễn giải. Có thể trả lời đủ chi tiết nếu khái niệm dễ bị hiểu sai.
- Nếu câu hỏi là vì sao/nguyên nhân/phân tích mà thiếu quốc gia/năm/ngữ cảnh dữ liệu, dùng cấu trúc rõ ràng như: Nhận định chung; Cơ chế tác động; Một số nguyên nhân có thể; Điều cần kiểm chứng thêm; Kết luận tham khảo.
- Nếu câu hỏi hỏi nguồn dữ liệu, giải thích nguồn, phạm vi sử dụng và giới hạn/cập nhật dữ liệu.
- Không dùng Markdown đậm/nghiêng.
- Với câu hỏi định nghĩa, bắt buộc dùng đúng bốn nhãn: "Định nghĩa ngắn gọn:", "Cách hiểu trong phân tích kinh tế:", "Ví dụ đơn giản:", "Lưu ý khi diễn giải:".
- Với câu hỏi vì sao/nguyên nhân/phân tích thiếu ngữ cảnh cụ thể, ưu tiên các nhãn rõ ràng và luôn có lưu ý rằng đây là giả thuyết tham khảo, không phải bằng chứng nhân quả.

USER_QUESTION:
{message}

KNOWLEDGE_CONTEXT:
{_safe_json([snippet.to_dict() for snippet in snippets])}
""".strip()
    return generate_gemini_text(prompt, model=model)


def _compose_template(message: str, snippets: list[KnowledgeSnippet]) -> str:
    primary = snippets[0] if snippets else None
    normalized = normalize_knowledge_text(message)

    if not primary:
        return (
            "Đây là câu hỏi giải thích trong phạm vi dữ liệu kinh tế - xã hội của hệ thống.\n\n"
            "Cách hiểu: hệ thống có thể hỗ trợ giải thích chỉ số, nguồn dữ liệu, xu hướng, bất thường và phân cụm.\n\n"
            "Lưu ý: với câu hỏi nguyên nhân, cần kiểm chứng thêm bằng dữ liệu cụ thể theo quốc gia và giai đoạn."
        )

    if _asks_source(normalized):
        return _source_answer(snippets)

    if _asks_reason(normalized):
        return _reason_answer(primary)

    return _definition_answer(primary)


def _definition_answer(snippet: KnowledgeSnippet) -> str:
    return (
        f"Định nghĩa ngắn gọn: {snippet.definition}\n\n"
        f"Cách hiểu trong phân tích kinh tế: {snippet.how_to_interpret}\n\n"
        f"Ví dụ đơn giản: {snippet.example}\n\n"
        f"Lưu ý khi diễn giải: {snippet.caveat}"
    )


def _reason_answer(snippet: KnowledgeSnippet) -> str:
    topic = snippet.title
    return (
        f"Nhận định chung: {topic} cần được hiểu như một tín hiệu mô tả. Một biến tăng hoặc giảm có thể phản ánh thay đổi kinh tế thật, "
        "nhưng bản thân một chỉ số chưa đủ để chứng minh nguyên nhân.\n\n"
        f"Cơ chế tác động: {snippet.how_to_interpret} Khi chỉ số biến động, cần xem biến đó đang nằm ở tử số, mẫu số hay là một tỷ lệ/chênh lệch. "
        "Ví dụ, một tỷ lệ có thể tăng vì biến chính tăng, vì quy mô nền kinh tế ở mẫu số giảm, hoặc vì cả hai cùng thay đổi với tốc độ khác nhau.\n\n"
        f"Một số nguyên nhân có thể: {snippet.example} Ngoài ra, kết quả có thể liên quan đến chu kỳ tăng trưởng, lạm phát, tỷ giá, thị trường lao động, "
        "đầu tư, thu chi ngân sách, cú sốc bên ngoài, thay đổi chính sách hoặc cập nhật phương pháp ghi nhận dữ liệu.\n\n"
        "Điều cần kiểm chứng thêm: cần xác định quốc gia, giai đoạn, mức thay đổi, các năm liền trước/liền sau và nhóm chỉ số liên quan. "
        "Nên đối chiếu với tăng trưởng GDP thực, lạm phát CPI, thất nghiệp, đầu tư/GDP, thương mại/GDP, cán cân ngân sách, nợ công/GDP và ghi chú nguồn dữ liệu nếu phù hợp.\n\n"
        "Kết luận tham khảo: các nguyên nhân trên là giả thuyết kinh tế hợp lý để định hướng kiểm tra, không phải bằng chứng nhân quả. "
        "Cần kiểm chứng bằng dữ liệu cụ thể trước khi rút ra kết luận chính sách."
    )


def _source_answer(snippets: list[KnowledgeSnippet]) -> str:
    source_snippets = [snippet for snippet in snippets if snippet.type == "data_source"]
    capability = next((snippet for snippet in snippets if snippet.type == "system_capability"), None)
    if not source_snippets:
        source_snippets = snippets[:3]

    source_lines = [
        f"- {snippet.title}: {snippet.definition} {snippet.how_to_interpret}".strip()
        for snippet in source_snippets[:3]
    ]
    caveats = [
        snippet.caveat
        for snippet in source_snippets[:3]
        if snippet.caveat
    ]
    scope = capability.how_to_interpret if capability else "Hệ thống dùng các nguồn đã chuẩn hóa trong phạm vi dự án cho so sánh, xu hướng, bất thường, giải thích chỉ số và giới hạn dữ liệu."

    return (
        "Nguồn dữ liệu chính:\n"
        + "\n".join(source_lines)
        + f"\n\nPhạm vi sử dụng: {scope}\n\n"
        + "Lưu ý: "
        + " ".join(caveats)
    )


def _asks_reason(normalized: str) -> bool:
    return any(token in normalized for token in ("vi sao", "tai sao", "nguyen nhan", "ly do", "phan tich"))


def _asks_source(normalized: str) -> bool:
    return any(token in normalized for token in ("du lieu lay tu dau", "nguon du lieu", "wdi", "faostat", "gmd", "world bank", "fao"))


def _is_acceptable_answer(message: str, answer: str) -> bool:
    text = str(answer or "").strip()
    if len(text) < 40:
        return False
    lowered = text.lower()
    forbidden = ("parser", "bigquery", "api", "route", "endpoint", "cloud run", "kaggle", "ngrok", "sql", "debug", "secret", "token")
    if any(token in lowered for token in forbidden):
        return False
    normalized = normalize_knowledge_text(message)
    if _asks_source(normalized):
        return "nguồn" in lowered or "source" in lowered
    if _asks_reason(normalized):
        return _is_acceptable_analysis_answer(text, lowered)
    return all(label in text for label in ("Định nghĩa ngắn gọn:", "Cách hiểu trong phân tích kinh tế:", "Ví dụ đơn giản:", "Lưu ý khi diễn giải:"))


def _is_acceptable_analysis_answer(text: str, lowered: str) -> bool:
    if len(text) < 220:
        return False
    section_markers = (
        "nhận định",
        "cơ chế",
        "nguyên nhân",
        "giả thuyết",
        "kiểm chứng",
        "kiểm tra",
        "kết luận",
        "lưu ý",
    )
    has_section_marker = any(marker in lowered for marker in section_markers)
    has_caveat = any(marker in lowered for marker in ("tham khảo", "không phải bằng chứng", "không chứng minh", "nhân quả", "cần kiểm chứng"))
    return bool(has_section_marker and has_caveat)


def _safe_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)
