from __future__ import annotations

import json
from typing import Any

from app.composer.display_formatter import format_value, get_country_label, get_direction_text, get_indicator_label, get_indicator_unit, safe_number
from app.core.config import settings
from app.knowledge.knowledge_retriever import KnowledgeSnippet
from app.llm.gemini_client import GeminiClientError, generate_gemini_text, is_gemini_enabled


FORBIDDEN_INTERNAL_TERMS = (
    "parser",
    "bigquery",
    "api",
    "route",
    "endpoint",
    "cloud run",
    "kaggle",
    "ngrok",
    "sql",
    "debug",
    "secret",
    "token",
)


def compose_provided_facts_analysis(
    message: str,
    facts: dict[str, Any],
    snippets: list[KnowledgeSnippet],
) -> tuple[str, str]:
    if settings.gemini_composer_enabled and is_gemini_enabled():
        for model in _candidate_models():
            try:
                answer = _compose_with_gemini(message, facts, snippets, model)
                if _is_acceptable_provided_facts_answer(answer, facts):
                    return answer, "gemini"
            except GeminiClientError:
                continue

    return _compose_template(facts, snippets), "template"


def compose_followup_deep_analysis(
    message: str,
    context_summary: dict[str, Any],
    rows: list[dict[str, Any]],
    question_type: str | None,
    snippets: list[KnowledgeSnippet],
) -> tuple[str, str]:
    if settings.gemini_composer_enabled and is_gemini_enabled():
        for model in _candidate_models():
            try:
                answer = _compose_followup_with_gemini(message, context_summary, rows, question_type, snippets, model)
                if _is_acceptable_followup_answer(answer):
                    return answer, "gemini"
            except GeminiClientError:
                continue

    return _compose_followup_template(message, context_summary, rows, question_type, snippets), "template"


def _candidate_models() -> list[str | None]:
    models: list[str | None] = [
        settings.ai_knowledge_model or settings.ai_composer_model or settings.gemini_model,
    ]
    if settings.ai_fallback_model:
        models.append(settings.ai_fallback_model)
    return models


def _compose_with_gemini(
    message: str,
    facts: dict[str, Any],
    snippets: list[KnowledgeSnippet],
    model: str | None,
) -> str:
    prompt = f"""
Bạn là trợ lý phân tích dữ liệu kinh tế - xã hội cho dashboard chính sách.

Nhiệm vụ:
- Trả lời bằng tiếng Việt, sâu và hữu ích cho phần demo phân tích.
- Chỉ coi PROVIDED_FACTS là số liệu chắc chắn được người dùng cung cấp.
- Có thể dùng KNOWLEDGE_CONTEXT và kiến thức kinh tế phổ thông để nêu giả thuyết hợp lý.
- Mọi giả thuyết nguyên nhân phải ghi rõ là tham khảo và cần kiểm chứng bằng dữ liệu; không khẳng định quan hệ nhân quả chắc chắn.
- Không bịa thêm số liệu định lượng ngoài PROVIDED_FACTS.
- Không nhắc các thuật ngữ nội bộ như parser, BigQuery, API, route, endpoint, Cloud Run, Kaggle, ngrok, SQL, debug, secret, token.
- Bắt buộc nhắc lại quốc gia, năm, giá trị chỉ số và điểm bất thường nếu có trong PROVIDED_FACTS.
- Dùng đúng 7 mục sau:
  1. Tóm tắt tín hiệu bất thường
  2. Cách hiểu chỉ số
  3. Ý nghĩa kinh tế có thể
  4. Các giả thuyết/nguyên nhân có thể
  5. Tác động hoặc rủi ro cần chú ý
  6. Dữ liệu/chỉ số nên kiểm tra thêm
  7. Lưu ý tham khảo

USER_QUESTION:
{message}

PROVIDED_FACTS:
{_safe_json(facts)}

KNOWLEDGE_CONTEXT:
{_safe_json([snippet.to_dict() for snippet in snippets])}
""".strip()
    return generate_gemini_text(prompt, model=model)


def _compose_followup_with_gemini(
    message: str,
    context_summary: dict[str, Any],
    rows: list[dict[str, Any]],
    question_type: str | None,
    snippets: list[KnowledgeSnippet],
    model: str | None,
) -> str:
    prompt_payload = {
        "user_message": message,
        "question_type": question_type,
        "previous_result_context": context_summary,
        "rows": _truncate_rows(rows, 60),
        "knowledge_context": [snippet.to_dict() for snippet in snippets],
    }
    prompt = f"""
Bạn là trợ lý phân tích dữ liệu kinh tế - xã hội cho dashboard chính sách.

Nhiệm vụ:
- Trả lời bằng tiếng Việt, trang trọng, rõ ràng, đủ sâu để dùng trong demo.
- Đây là câu hỏi tiếp nối. Phải dựa trên previous_result_context và rows được cung cấp.
- Tách rõ: dữ liệu trước đó cho thấy gì, đâu là giả thuyết/diễn giải kinh tế cần kiểm chứng.
- Có thể dùng kiến thức kinh tế phổ thông để nêu giả thuyết hợp lý, nhưng không được khẳng định quan hệ nhân quả chắc chắn.
- Không bịa số liệu ngoài dữ liệu đầu vào. Nếu thiếu số để kết luận, nói rõ cần kiểm tra thêm.
- Nếu previous_result_context là xếp hạng một năm, không gọi đó là xu hướng thời gian.
- Nếu người dùng hỏi "làm rõ hơn" hoặc "phân tích kĩ hơn", hãy mở rộng phân tích trước đó thay vì trả lời một câu ngắn.
- Không nhắc các thuật ngữ nội bộ như parser, BigQuery, API, route, endpoint, Cloud Run, Kaggle, ngrok, SQL, debug, secret, token.
- Dùng Markdown có chủ đích với các tiêu đề `###` và bullet list để dễ đọc.
- Câu trả lời nên có các mục:
  ### Dựa trên kết quả trước
  ### Điều dữ liệu cho thấy
  ### Các giả thuyết/nguyên nhân có thể
  ### Tác động hoặc rủi ro cần chú ý
  ### Cần kiểm tra thêm
  ### Gợi ý phân tích tiếp
  ### Lưu ý tham khảo
- Kết thúc bằng lưu ý rõ rằng đây là phân tích tham khảo, không phải bằng chứng nhân quả, và cần kiểm chứng bằng dữ liệu/bối cảnh.

INPUT:
{_safe_json(prompt_payload)}
""".strip()
    return generate_gemini_text(prompt, model=model)


def _compose_followup_template(
    message: str,
    context_summary: dict[str, Any],
    rows: list[dict[str, Any]],
    question_type: str | None,
    snippets: list[KnowledgeSnippet],
) -> str:
    indicator_code = str(context_summary.get("indicator") or "")
    indicator_label = str(context_summary.get("indicator_label") or get_indicator_label(indicator_code))
    unit = str(context_summary.get("unit") or get_indicator_unit(indicator_code))
    period = _period_text(context_summary)
    observed = _observed_context_text(context_summary, rows, question_type, indicator_label, unit, period)
    data_insight = _data_insight_text(context_summary, rows, question_type, indicator_label, unit)
    hypotheses = _indicator_followup_hypotheses(indicator_code, indicator_label, question_type)
    risks = _indicator_followup_risks(indicator_code, indicator_label, question_type)
    checks = _indicator_followup_checks(indicator_code, indicator_label, question_type)
    suggestions = _followup_suggestions(indicator_code, indicator_label, question_type)
    snippet_note = _snippet_context(snippets)
    snippet_sentence = f"\n\nBối cảnh khái niệm liên quan: {snippet_note}" if snippet_note else ""

    return (
        "### Dựa trên kết quả trước\n"
        f"{observed}{snippet_sentence}\n\n"
        "### Điều dữ liệu cho thấy\n"
        f"{data_insight}\n\n"
        "### Các giả thuyết/nguyên nhân có thể\n"
        f"{hypotheses}\n\n"
        "### Tác động hoặc rủi ro cần chú ý\n"
        f"{risks}\n\n"
        "### Cần kiểm tra thêm\n"
        f"{checks}\n\n"
        "### Gợi ý phân tích tiếp\n"
        f"{suggestions}\n\n"
        "### Lưu ý tham khảo\n"
        "Phân tích trên chỉ là diễn giải tham khảo dựa trên kết quả đã hiển thị và kiến thức kinh tế phổ thông. "
        "Nó không phải bằng chứng nhân quả; cần kiểm chứng bằng chuỗi dữ liệu đầy đủ, ghi chú nguồn và bối cảnh chính sách của từng quốc gia."
    )


def _compose_template(facts: dict[str, Any], snippets: list[KnowledgeSnippet]) -> str:
    country = str(facts.get("country_name") or facts.get("country_code") or "quốc gia được nêu")
    year = facts.get("year") or "năm được nêu"
    indicator_code = str(facts.get("indicator_code") or "")
    indicator_label = str(facts.get("indicator_label") or get_indicator_label(indicator_code))
    unit = str(facts.get("unit") or "")
    value = facts.get("value")
    anomaly_score = facts.get("anomaly_score")
    value_text = format_value(value, unit) if value is not None else "không được nêu"
    score_text = _format_score(anomaly_score)
    snippet_context = _snippet_context(snippets)

    if indicator_code == "GDP_pc_growth_gap":
        indicator_explanation = (
            "Chỉ số này nên được đọc như độ chênh giữa tăng trưởng GDP tổng thể và tăng trưởng GDP bình quân đầu người. "
            "Nó liên quan trực tiếp đến câu hỏi: sản lượng của nền kinh tế tăng nhanh hơn, chậm hơn hay chỉ vừa đủ bù cho thay đổi dân số."
        )
        economic_meaning = (
            f"Với {country} năm {year}, mức {value_text} cho thấy phần chênh lệch được ghi nhận là đáng kể trong thang đo phần trăm. "
            "Nếu chênh lệch dương, tăng trưởng tổng sản lượng có thể đang vượt tăng trưởng tính trên mỗi người; điều này thường hàm ý tăng trưởng quy mô "
            "chưa chắc chuyển hóa hoàn toàn thành cải thiện thu nhập/sản lượng bình quân cho mỗi người. Nếu cách tính trong dữ liệu dùng chênh lệch so với xu hướng "
            "hoặc chuẩn tham chiếu, giá trị này có thể phản ánh một năm lệch khỏi quỹ đạo thông thường."
        )
        hypotheses = (
            "Các giả thuyết tham khảo gồm: GDP thực hoặc GDP danh nghĩa tăng nhanh hơn thường lệ; tốc độ tăng dân số thay đổi làm mẫu số GDP bình quân đầu người biến động; "
            "năng suất lao động, đầu tư hoặc khai thác công suất cải thiện; dịch chuyển ngành như xây dựng, năng lượng, du lịch, xuất khẩu hoặc kiều hối phục hồi; "
            "chính sách tài khóa/tiền tệ hỗ trợ cầu nội địa; lạm phát hoặc tỷ giá làm thay đổi cách đọc chỉ số danh nghĩa; hiệu ứng nền sau một năm yếu; "
            "hoặc dữ liệu nguồn được hiệu chỉnh, thay đổi độ phủ hay phương pháp ghi nhận."
        )
        risks = (
            "Rủi ro chính là diễn giải quá mức: một tín hiệu cao có thể là tăng trưởng thực chất, nhưng cũng có thể chỉ là hiệu ứng nền, thay đổi dân số, "
            "lạm phát/tỷ giá hoặc cập nhật dữ liệu. Với GDP bình quân đầu người, cần chú ý liệu tăng trưởng có lan tỏa sang thu nhập hộ gia đình, việc làm và năng suất hay không."
        )
        checks = (
            "Nên kiểm tra tăng trưởng GDP thực, tăng trưởng GDP danh nghĩa, tăng trưởng dân số, lạm phát CPI, tỷ giá nếu có, đầu tư cố định/GDP, thương mại/GDP, "
            "thất nghiệp, năng suất hoặc chỉ báo lao động, cán cân ngân sách/GDP, nợ công/GDP, cùng các năm trước và sau 2025 để phân biệt cú sốc một năm với thay đổi xu hướng."
        )
    elif indicator_code == "inflation_cpi":
        indicator_explanation = (
            "Lạm phát CPI đo tốc độ tăng mặt bằng giá tiêu dùng. Khi chỉ số này bất thường, câu hỏi trung tâm là áp lực giá đến từ cầu, chi phí đầu vào, tỷ giá, "
            "chính sách hay yếu tố thống kê."
        )
        economic_meaning = (
            f"Với {country} năm {year}, mức {value_text} là tín hiệu giá tiêu dùng tăng rất mạnh nếu dữ liệu được đọc theo đơn vị phần trăm. "
            "Điều này có thể bào mòn sức mua, làm lãi suất thực biến động, gây áp lực lên kỳ vọng lạm phát và làm chính sách ổn định vĩ mô khó hơn."
        )
        hypotheses = (
            "Các giả thuyết tham khảo gồm: mất giá tiền tệ làm giá nhập khẩu tăng; cú sốc năng lượng hoặc lương thực; chính sách tiền tệ/tài khóa nới lỏng; "
            "đứt gãy cung ứng; điều chỉnh giá do nhà nước quản lý; hiệu ứng nền; hoặc thay đổi rổ hàng hóa, phương pháp đo hay cập nhật dữ liệu."
        )
        risks = (
            "Rủi ro cần chú ý là lạm phát lan sang tiền lương, lãi suất, tỷ giá và sức mua hộ gia đình. Nếu cú sốc kéo dài, doanh nghiệp và hộ gia đình có thể điều chỉnh kỳ vọng theo hướng bất lợi."
        )
        checks = (
            "Nên kiểm tra lạm phát lõi nếu có, tỷ giá, lãi suất danh nghĩa và lãi suất thực, giá năng lượng/lương thực, tăng trưởng tiền tệ, cán cân tài khóa, thất nghiệp, "
            "tăng trưởng GDP thực, cùng dữ liệu các năm trước và sau năm bất thường."
        )
    else:
        indicator_explanation = (
            f"{indicator_label} cần được hiểu theo định nghĩa và đơn vị của chỉ số. "
            f"{snippet_context or 'Nên đọc chỉ số này cùng xu hướng nhiều năm, bối cảnh quốc gia và các biến liên quan.'}"
        )
        economic_meaning = (
            f"Với {country} năm {year}, giá trị {value_text} đi kèm điểm bất thường {score_text} cho thấy quan sát này lệch đáng kể so với mẫu hình tham chiếu trong dữ liệu. "
            "Về kinh tế, đây là tín hiệu nên điều tra sâu hơn vì nó có thể phản ánh thay đổi thực trong nền kinh tế, cú sốc tạm thời, hoặc thay đổi trong cách dữ liệu được ghi nhận."
        )
        hypotheses = (
            "Các giả thuyết tham khảo gồm: thay đổi chu kỳ tăng trưởng; cú sốc bên ngoài; điều chỉnh chính sách tài khóa, tiền tệ hoặc thương mại; thay đổi cơ cấu ngành; "
            "biến động dân số, thị trường lao động hoặc giá cả; hiệu ứng nền; cập nhật dữ liệu nguồn; thay đổi phương pháp thống kê hoặc độ phủ quan sát."
        )
        risks = (
            "Rủi ro là dùng một điểm dữ liệu đơn lẻ để kết luận chính sách. Bất thường có thể là tín hiệu kinh tế quan trọng, nhưng cũng có thể là nhiễu thống kê hoặc hiệu chỉnh nguồn."
        )
        checks = (
            "Nên kiểm tra chuỗi nhiều năm trước/sau, chỉ số cùng nhóm, tăng trưởng GDP thực, lạm phát CPI, tỷ giá nếu liên quan, thất nghiệp, đầu tư/GDP, thương mại/GDP, "
            "cán cân ngân sách/GDP, nợ công/GDP và ghi chú nguồn dữ liệu."
        )

    return (
        f"1. Tóm tắt tín hiệu bất thường\n"
        f"Với {country} năm {year}, {indicator_label} được cung cấp là {value_text}; điểm bất thường thống kê là {score_text}. "
        f"Điểm {score_text} nên được xem là tín hiệu bất thường mạnh trong khung thống kê của hệ thống, tức quan sát này đáng được phân tích kỹ thay vì chỉ đọc như một giá trị riêng lẻ.\n\n"
        "2. Cách hiểu chỉ số\n"
        f"{indicator_explanation}\n\n"
        "3. Ý nghĩa kinh tế có thể\n"
        f"{economic_meaning}\n\n"
        "4. Các giả thuyết/nguyên nhân có thể\n"
        f"{hypotheses}\n\n"
        "5. Tác động hoặc rủi ro cần chú ý\n"
        f"{risks}\n\n"
        "6. Dữ liệu/chỉ số nên kiểm tra thêm\n"
        f"{checks}\n\n"
        "7. Lưu ý tham khảo\n"
        "Các nhận định trên là giả thuyết kinh tế để tham khảo, dựa trên số liệu người dùng cung cấp và kiến thức kinh tế phổ thông. "
        "Chúng không phải bằng chứng nhân quả hay kết luận rằng dữ liệu đúng/sai; cần kiểm chứng bằng chuỗi dữ liệu, nguồn gốc thống kê và bối cảnh chính sách cụ thể."
    )


def _is_acceptable_provided_facts_answer(answer: str, facts: dict[str, Any]) -> bool:
    text = str(answer or "").strip()
    if len(text) < 650:
        return False

    lowered = text.lower()
    if any(term in lowered for term in FORBIDDEN_INTERNAL_TERMS):
        return False

    required_markers = (
        "Tóm tắt",
        "Cách hiểu",
        "Ý nghĩa",
        "giả thuyết",
        "kiểm tra",
        "tham khảo",
    )
    if not all(marker.lower() in lowered for marker in required_markers):
        return False

    if "nhân quả" not in lowered and "cần kiểm chứng" not in lowered:
        return False

    country = str(facts.get("country_name") or facts.get("country_code") or "").strip()
    if country and country.lower() not in lowered:
        return False

    year = facts.get("year")
    if year is not None and str(year) not in text:
        return False

    value = facts.get("value")
    if value is not None and _number_token(value) not in _normalized_number_text(text):
        return False

    anomaly_score = facts.get("anomaly_score")
    if anomaly_score is not None and _number_token(anomaly_score) not in _normalized_number_text(text):
        return False

    return True


def _is_acceptable_followup_answer(answer: str) -> bool:
    text = str(answer or "").strip()
    if len(text) < 900:
        return False
    lowered = text.lower()
    if any(term in lowered for term in FORBIDDEN_INTERNAL_TERMS):
        return False
    required = (
        ("dựa trên", "kết quả trước", "dữ liệu"),
        ("giả thuyết", "nguyên nhân", "yếu tố"),
        ("rủi ro", "tác động", "ảnh hưởng"),
        ("kiểm tra", "kiểm chứng", "đối chiếu"),
        ("tham khảo", "nhân quả", "cần kiểm chứng"),
    )
    return all(any(marker in lowered for marker in group) for group in required)


def _truncate_rows(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    safe_rows = rows if isinstance(rows, list) else []
    return safe_rows[: max(0, limit)]


def _period_text(context_summary: dict[str, Any]) -> str:
    year = context_summary.get("year")
    start_year = context_summary.get("start_year")
    end_year = context_summary.get("end_year")
    years = context_summary.get("years") or []
    if year:
        return f" năm {year}"
    if start_year and end_year:
        return f" giai đoạn {start_year}-{end_year}" if start_year != end_year else f" năm {start_year}"
    if len(years) == 1:
        return f" năm {years[0]}"
    if len(years) >= 2:
        return f" giai đoạn {years[0]}-{years[-1]}"
    return ""


def _observed_context_text(
    context_summary: dict[str, Any],
    rows: list[dict[str, Any]],
    question_type: str | None,
    indicator_label: str,
    unit: str,
    period: str,
) -> str:
    row_count = context_summary.get("row_count")
    row_count_text = f" với {row_count} quan sát" if row_count else ""
    if question_type == "VALID_RANKING_QUERY":
        ranking_lines = _ranking_lines(rows, unit)
        ranking_intro = (
            f"Kết quả trước là bảng xếp hạng {indicator_label}{period}{row_count_text}. "
            "Đây là lát cắt tại một năm hoặc một thời điểm, không phải xu hướng thời gian."
        )
        return f"{ranking_intro}\n\n{ranking_lines}" if ranking_lines else ranking_intro

    series_summary = context_summary.get("series_summary") or []
    if isinstance(series_summary, list) and series_summary:
        lines = []
        for item in series_summary[:8]:
            if not isinstance(item, dict):
                continue
            country = item.get("country") or item.get("country_code") or "quốc gia"
            first_year = item.get("first_year")
            last_year = item.get("last_year")
            first_value = format_value(item.get("first_value"), unit)
            last_value = format_value(item.get("last_value"), unit)
            direction = item.get("direction") or "chưa rõ"
            lines.append(f"- {country}: {first_value} năm {first_year} đến {last_value} năm {last_year} ({direction}).")
        if lines:
            return (
                f"Kết quả trước theo dõi {indicator_label}{period}{row_count_text}. "
                "Các điểm đầu/cuối theo quốc gia từ toàn bộ kết quả đã lưu là:\n"
                + "\n".join(lines)
            )

    if rows:
        compact_lines = _compact_row_lines(rows, unit)
        return (
            f"Kết quả trước liên quan đến {indicator_label}{period}{row_count_text}. "
            "Một số quan sát trong context hiện có:\n"
            + compact_lines
        )

    return f"Kết quả trước liên quan đến {indicator_label}{period}{row_count_text}, nhưng context hiện không có đủ dòng chi tiết để đọc từng quan sát."


def _data_insight_text(
    context_summary: dict[str, Any],
    rows: list[dict[str, Any]],
    question_type: str | None,
    indicator_label: str,
    unit: str,
) -> str:
    if question_type == "VALID_RANKING_QUERY":
        order = context_summary.get("order")
        order_text = "cao nhất" if order == "desc" else "thấp nhất" if order == "asc" else "nổi bật"
        first = _first_numeric_row(rows)
        if first:
            country = get_country_label(first)
            return (
                f"Dữ liệu đang nhấn mạnh nhóm quốc gia có {indicator_label} {order_text}; quan sát nổi bật đầu bảng là "
                f"{country} với mức {format_value(_row_value(first), unit)}. Vì đây là xếp hạng tại một lát cắt, nên phân tích nên tập trung vào "
                "đặc điểm chung của nhóm và các yếu tố có thể làm chỉ số cao/thấp trong năm đó, không diễn giải như xu hướng dài hạn."
            )
        return (
            f"Dữ liệu đang nhấn mạnh nhóm quốc gia có {indicator_label} {order_text}. Vì đây là xếp hạng, cần phân tích đặc điểm nhóm thay vì kết luận xu hướng."
        )

    series_summary = context_summary.get("series_summary") or []
    if isinstance(series_summary, list) and len(series_summary) >= 2:
        return (
            f"Dữ liệu cho thấy khác biệt động học giữa các quốc gia về {indicator_label}: một số nước tăng, một số nước giảm hoặc tăng chậm hơn. "
            "Vì vậy, câu hỏi nguyên nhân nên được đọc theo cơ chế riêng của từng nước: thay đổi ở biến chính, thay đổi ở mẫu số, cú sốc vĩ mô và cách dữ liệu được cập nhật."
        )
    if isinstance(series_summary, list) and len(series_summary) == 1:
        item = series_summary[0]
        return (
            f"Dữ liệu cho thấy {indicator_label} của {item.get('country') or item.get('country_code') or 'quốc gia này'} "
            f"có hướng {item.get('direction') or 'biến động'} trong giai đoạn quan sát. Cần tách phần biến động do yếu tố kinh tế thực với phần có thể đến từ hiệu ứng nền hoặc thay đổi dữ liệu."
        )
    return (
        f"Dữ liệu trước đó cung cấp tín hiệu mô tả về {indicator_label}. Tín hiệu này đủ để đặt giả thuyết phân tích, nhưng chưa đủ để kết luận nguyên nhân nếu chưa đối chiếu thêm chỉ số liên quan."
    )


def _indicator_followup_hypotheses(indicator_code: str, indicator_label: str, question_type: str | None) -> str:
    if indicator_code == "govdebt_GDP":
        return (
            "- Thâm hụt ngân sách kéo dài có thể làm nợ danh nghĩa tăng nhanh hơn GDP.\n"
            "- Tăng trưởng GDP chậm làm mẫu số nhỏ đi tương đối, khiến nợ/GDP tăng ngay cả khi vay mới không tăng đột biến.\n"
            "- Chi phí lãi vay cao hơn làm nghĩa vụ trả nợ tích lũy nhanh hơn.\n"
            "- Nếu có nợ ngoại tệ, biến động tỷ giá có thể làm giá trị nợ quy đổi tăng.\n"
            "- Các cú sốc như đại dịch, suy giảm cầu hoặc hỗ trợ tài khóa khẩn cấp có thể làm chi tiêu công tăng trong một số năm.\n"
            "- Khác biệt giữa các nước có thể đến từ tốc độ củng cố tài khóa, năng lực thu ngân sách, cơ cấu kỳ hạn nợ và cách ghi nhận nợ công."
        )
    if indicator_code == "inflation_cpi" or question_type == "VALID_RANKING_QUERY":
        return (
            "- Lạm phát cao trong một nhóm nước có thể liên quan đến mất giá tiền tệ, nhập khẩu lạm phát hoặc cú sốc giá năng lượng/lương thực.\n"
            "- Chính sách tiền tệ nới lỏng, tài khóa căng thẳng hoặc kỳ vọng lạm phát kém ổn định có thể làm áp lực giá kéo dài.\n"
            "- Đứt gãy cung ứng, xung đột, bất ổn chính trị hoặc kiểm soát giá được điều chỉnh lại có thể tạo cú sốc một năm.\n"
            "- Với bảng xếp hạng một năm, hiệu ứng nền và cập nhật phương pháp thống kê cũng có thể làm một số nước nổi bật."
        )
    if indicator_code in {"GDP_pc_growth_gap", "rGDP_growth_YoY", "GDP_growth_YoY", "trend_deviation", "rolling_mean_5yr"}:
        return (
            "- Tăng trưởng có thể thay đổi do đầu tư, năng suất, cầu nội địa, xuất khẩu, du lịch, kiều hối hoặc chuyển dịch cơ cấu ngành.\n"
            "- Với GDP bình quân đầu người hoặc chênh lệch tăng trưởng, tăng dân số và thay đổi lực lượng lao động là cơ chế quan trọng.\n"
            "- Hiệu ứng nền sau một năm yếu có thể làm tốc độ tăng trông cao bất thường.\n"
            "- Lạm phát, tỷ giá hoặc cập nhật nguồn dữ liệu có thể ảnh hưởng cách đọc các chỉ số danh nghĩa hoặc chỉ số được tính lại."
        )
    return (
        f"- {indicator_label} có thể chịu tác động từ chu kỳ tăng trưởng, chính sách công, cú sốc bên ngoài, thay đổi cơ cấu ngành và thị trường lao động.\n"
        "- Cần xét cả tử số, mẫu số và đơn vị đo nếu đây là tỷ lệ/chênh lệch.\n"
        "- Hiệu ứng nền, độ trễ cập nhật, thay đổi phương pháp ghi nhận hoặc độ phủ dữ liệu có thể làm kết quả nổi bật mà không hàm ý thay đổi cơ bản."
    )


def _indicator_followup_risks(indicator_code: str, indicator_label: str, question_type: str | None) -> str:
    if indicator_code == "govdebt_GDP":
        return (
            "- Nợ/GDP tăng có thể thu hẹp dư địa tài khóa cho đầu tư công và hỗ trợ chu kỳ khi có cú sốc.\n"
            "- Gánh nặng trả lãi có thể cạnh tranh với chi tiêu xã hội hoặc hạ tầng.\n"
            "- Nếu thị trường nghi ngờ khả năng ổn định nợ, chi phí vay và niềm tin nhà đầu tư có thể xấu đi.\n"
            "- Tuy vậy, mức nợ cần được đánh giá cùng tăng trưởng, lãi suất, kỳ hạn nợ, đồng tiền vay và năng lực thu ngân sách."
        )
    if indicator_code == "inflation_cpi" or question_type == "VALID_RANKING_QUERY":
        return (
            "- Lạm phát cao có thể bào mòn sức mua, làm thu nhập thực giảm và tăng áp lực an sinh.\n"
            "- Lãi suất cao hơn để kiềm chế giá có thể làm chi phí vốn tăng và ảnh hưởng đầu tư.\n"
            "- Biến động tỷ giá và kỳ vọng giá có thể tạo vòng phản hồi khiến ổn định vĩ mô khó hơn.\n"
            "- Với xếp hạng một năm, rủi ro diễn giải là nhầm một cú sốc tạm thời với trạng thái kéo dài."
        )
    return (
        f"- Biến động mạnh của {indicator_label} có thể ảnh hưởng cách đánh giá ổn định vĩ mô, dư địa chính sách và triển vọng tăng trưởng.\n"
        "- Rủi ro chính là kết luận quá nhanh từ một lát cắt hoặc một số dòng dữ liệu khi chưa kiểm tra chuỗi dài hơn.\n"
        "- Nếu chỉ số liên quan đến tỷ lệ, thay đổi mẫu số có thể tạo tín hiệu mạnh dù biến chính không thay đổi tương ứng."
    )


def _indicator_followup_checks(indicator_code: str, indicator_label: str, question_type: str | None) -> str:
    if indicator_code == "govdebt_GDP":
        return (
            "- Cán cân ngân sách/GDP, thu ngân sách/GDP và chi ngân sách/GDP.\n"
            "- Tăng trưởng GDP thực, lạm phát, lãi suất thực và chi phí trả lãi nếu có.\n"
            "- Tỷ giá hoặc REER nếu nợ ngoại tệ có vai trò lớn.\n"
            "- Nợ công/GDP các năm trước và sau giai đoạn đang xem để phân biệt xu hướng bền vững với cú sốc tạm thời.\n"
            "- Ghi chú nguồn về phạm vi nợ công: chính phủ trung ương, chính phủ chung hay khu vực công rộng hơn."
        )
    if indicator_code == "inflation_cpi" or question_type == "VALID_RANKING_QUERY":
        return (
            "- Lạm phát CPI các năm trước/sau để xem cú sốc có kéo dài không.\n"
            "- Tỷ giá, lãi suất danh nghĩa/lãi suất thực, cán cân tài khóa và tăng trưởng tiền tệ nếu có.\n"
            "- Giá năng lượng, lương thực, nhập khẩu và độ mở thương mại.\n"
            "- Tăng trưởng GDP thực, thất nghiệp và chính sách kiểm soát giá nếu có.\n"
            "- Ghi chú nguồn hoặc thay đổi rổ CPI/phương pháp đo."
        )
    return (
        f"- Chuỗi {indicator_label} nhiều năm trước và sau kết quả vừa xem.\n"
        "- Tăng trưởng GDP thực, lạm phát CPI, thất nghiệp, đầu tư/GDP, thương mại/GDP, cán cân ngân sách/GDP và nợ công/GDP nếu phù hợp.\n"
        "- Nhóm quốc gia so sánh hoặc benchmark khu vực để biết kết quả là riêng lẻ hay phổ biến.\n"
        "- Ghi chú nguồn dữ liệu, độ phủ và khả năng hiệu chỉnh."
    )


def _followup_suggestions(indicator_code: str, indicator_label: str, question_type: str | None) -> str:
    if question_type == "VALID_RANKING_QUERY":
        return (
            f"- So sánh nhóm đứng đầu với nhóm trung vị về {indicator_label} trong cùng năm.\n"
            "- Chuyển từ xếp hạng một năm sang chuỗi thời gian 5-10 năm cho các nước nổi bật.\n"
            "- Kiểm tra xem các nước đầu bảng có cùng khu vực, cùng cú sốc giá hoặc cùng biến động tỷ giá hay không."
        )
    if indicator_code == "govdebt_GDP":
        return (
            "- Vẽ cùng lúc nợ công/GDP và cán cân ngân sách/GDP để xem vai trò thâm hụt.\n"
            "- So sánh nợ công/GDP với tăng trưởng GDP thực để kiểm tra tác động mẫu số.\n"
            "- Tách phân tích theo từng nước thay vì gộp chung nếu xu hướng Việt Nam và Thái Lan khác nhau."
        )
    return (
        f"- Hỏi tiếp theo dạng: 'So sánh {indicator_label} với các chỉ số liên quan trong cùng giai đoạn'.\n"
        "- Xem thêm các năm liền trước/liền sau để kiểm tra độ bền của tín hiệu.\n"
        "- So sánh với nhóm nước cùng khu vực hoặc cùng mức phát triển để có benchmark phù hợp."
    )


def _ranking_lines(rows: list[dict[str, Any]], unit: str) -> str:
    lines = []
    for index, row in enumerate(rows[:10], start=1):
        country = get_country_label(row)
        year = row.get("year")
        value = format_value(_row_value(row), unit)
        year_text = f" năm {year}" if year else ""
        lines.append(f"- {index}. {country}{year_text}: {value}.")
    return "\n".join(lines)


def _compact_row_lines(rows: list[dict[str, Any]], unit: str) -> str:
    lines = []
    for row in rows[:12]:
        country = get_country_label(row)
        year = row.get("year")
        value = format_value(_row_value(row), unit)
        year_text = f" năm {year}" if year else ""
        lines.append(f"- {country}{year_text}: {value}.")
    return "\n".join(lines)


def _first_numeric_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    for row in rows:
        if safe_number(_row_value(row)) is not None:
            return row
    return None


def _row_value(row: dict[str, Any]) -> Any:
    if row.get("value") is not None:
        return row.get("value")
    if row.get("actual_value") is not None:
        return row.get("actual_value")
    return None


def build_series_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    safe_rows = rows if isinstance(rows, list) else []
    for row in safe_rows:
        if not isinstance(row, dict):
            continue
        country_code = str(row.get("country_code") or row.get("country") or "").strip()
        if not country_code:
            continue
        if safe_number(_row_value(row)) is None:
            continue
        grouped.setdefault(country_code, []).append(row)

    summaries: list[dict[str, Any]] = []
    for country_code, country_rows in grouped.items():
        country_rows.sort(key=lambda item: int(item.get("year") or 0))
        first = country_rows[0]
        last = country_rows[-1]
        values = [safe_number(_row_value(row)) for row in country_rows]
        numeric_values = [value for value in values if value is not None]
        summaries.append(
            {
                "country_code": country_code,
                "country": get_country_label(last, country_code=country_code),
                "first_year": first.get("year"),
                "first_value": _row_value(first),
                "last_year": last.get("year"),
                "last_value": _row_value(last),
                "direction": get_direction_text(_row_value(first), _row_value(last)),
                "min_value": min(numeric_values) if numeric_values else None,
                "max_value": max(numeric_values) if numeric_values else None,
                "observations": len(country_rows),
            }
        )
    return summaries


def _format_score(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "không được nêu"
    return f"{number:.3f}"


def _number_token(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value).replace(",", ".").strip()
    return f"{number:.3f}".rstrip("0").rstrip(".")


def _normalized_number_text(text: str) -> str:
    return str(text or "").replace(",", ".")


def _snippet_context(snippets: list[KnowledgeSnippet]) -> str:
    useful = [
        snippet
        for snippet in snippets
        if snippet.type in {"indicator", "analytics_concept"} and (snippet.definition or snippet.how_to_interpret)
    ]
    if not useful:
        return ""
    first = useful[0]
    return f"{first.definition} {first.how_to_interpret}".strip()


def _safe_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)
