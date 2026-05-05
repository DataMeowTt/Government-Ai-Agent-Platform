from __future__ import annotations

import re
from typing import Any

from app.composer.display_formatter import (
    format_value,
    format_year_range,
    get_country_label,
    get_direction_text,
    get_indicator_label,
    get_indicator_unit,
    replace_indicator_codes,
    safe_number,
)


def _row_value(row: dict) -> Any:
    if row.get("value") is not None:
        return row.get("value")
    return row.get("actual_value")


def _row_year(row: dict) -> int | None:
    year = row.get("year")
    try:
        return int(year)
    except (TypeError, ValueError):
        return None


def _group_rows_by_country(rows: list[dict]) -> list[tuple[str, list[dict]]]:
    grouped: dict[str, list[dict]] = {}
    labels: dict[str, str] = {}

    for row in rows:
        key = str(row.get("country_code") or row.get("country") or "UNKNOWN")
        grouped.setdefault(key, []).append(row)
        labels[key] = get_country_label(row)

    result = []
    for key, items in grouped.items():
        sorted_items = sorted(items, key=lambda row: (_row_year(row) is None, _row_year(row) or 0))
        result.append((labels.get(key) or key, sorted_items))
    return result


def _best_rows_by_value(rows: list[dict]) -> tuple[dict | None, dict | None]:
    numeric_rows = [row for row in rows if safe_number(_row_value(row)) is not None]
    if not numeric_rows:
        return None, None
    highest = max(numeric_rows, key=lambda row: safe_number(_row_value(row)) or float("-inf"))
    lowest = min(numeric_rows, key=lambda row: safe_number(_row_value(row)) or float("inf"))
    return highest, lowest


def compose_off_topic_answer() -> str:
    return (
        "Câu hỏi này nằm ngoài phạm vi dữ liệu chỉ số kinh tế, xã hội và quản trị hiện có. "
        "Bạn có thể hỏi về GDP, nợ công, lạm phát, thất nghiệp, nghèo đói, khủng hoảng, "
        "dân số, đô thị hóa, đầu tư hoặc thương mại."
    )


CLARIFICATION_FALLBACK = "Mình cần bạn nói rõ thêm chỉ số, quốc gia hoặc giai đoạn muốn phân tích."


def sanitize_clarification_questions(questions: list[str] | None) -> list[str]:
    sanitized: list[str] = []
    for question in questions or []:
        text = replace_indicator_codes(str(question or "").strip())
        lowered = text.lower()

        if not text:
            continue
        if "please clarify" in lowered or "missing or ambiguous slot" in lowered:
            text = "Bạn có thể nói rõ hơn chỉ số, quốc gia và giai đoạn muốn phân tích không?"
        elif "which indicator" in lowered or "compare or analyze which indicator" in lowered:
            text = "Bạn muốn phân tích chỉ số nào? Ví dụ: nợ công/GDP, lạm phát CPI, thất nghiệp, tăng trưởng GDP thực."
        elif "please specify" in lowered and ("country" in lowered or "countries" in lowered):
            text = "Bạn muốn xem cho quốc gia hoặc nhóm quốc gia nào?"
        elif "please specify" in lowered and ("time" in lowered or "year" in lowered or "period" in lowered):
            text = "Bạn muốn xem năm hoặc giai đoạn nào?"
        elif "please specify" in lowered:
            text = "Bạn có thể nói rõ hơn chỉ số, quốc gia và giai đoạn muốn phân tích không?"
        elif "indicator" in lowered and "chỉ số" not in lowered:
            text = "Bạn muốn phân tích chỉ số nào? Ví dụ: nợ công/GDP, lạm phát CPI, thất nghiệp, tăng trưởng GDP thực."

        sanitized.append(text)

    return sanitized


def compose_need_clarification_answer(questions: list[str] | None) -> str:
    cleaned = sanitize_clarification_questions(questions)
    if not cleaned:
        return CLARIFICATION_FALLBACK
    return "Mình cần bạn làm rõ thêm: " + " ".join(cleaned)


def _sanitize_warning(text: str) -> str | None:
    text = replace_indicator_codes(str(text or "").strip())
    if not text:
        return None

    lowered = text.lower()
    if any(
        token in lowered
        for token in (
            "planner",
            "parser",
            "router",
            "parsedquery",
            "query planner",
            "tool",
            "database",
            "db",
            "gemini",
            "ngrok",
            "kaggle",
        )
    ):
        return None
    if "unsupported indicator" in lowered:
        return None
    if "not supported" in lowered or "chưa được hỗ trợ" in lowered:
        return "Yêu cầu này hiện chưa được hỗ trợ trong dữ liệu hiện có."
    return text


def compose_unsupported_answer(warnings: list[str] | None = None) -> str:
    cleaned = [_sanitize_warning(warning) for warning in warnings or []]
    cleaned = [warning for warning in cleaned if warning]

    prefix = "Hiện hệ thống chưa hỗ trợ yêu cầu này trong dữ liệu hiện có."
    if cleaned:
        prefix = " ".join(cleaned)

    return (
        f"{prefix} Bạn có thể hỏi về các nhóm chỉ số đang hỗ trợ như GDP, nợ công/GDP, "
        "lạm phát CPI, thất nghiệp, thu thuế/GDP, cán cân ngân sách/GDP, đầu tư cố định gộp/GDP, "
        "thương mại/GDP, dân số, nghèo đói hoặc khủng hoảng."
    )


def compose_compare_answer(
    indicator_code: str | None,
    country_codes: list[str],
    start_year: int | None,
    end_year: int | None,
    rows: list[dict],
) -> str:
    label = get_indicator_label(indicator_code)
    unit = get_indicator_unit(indicator_code)
    period = format_year_range(start_year, end_year)

    if not rows:
        return f"Không tìm thấy dữ liệu phù hợp cho {label} trong {period}."

    lines = [f"So sánh {label} giai đoạn {period}:"]
    final_rows: list[dict] = []

    for country_label, items in _group_rows_by_country(rows):
        if not items:
            continue
        first = items[0]
        last = items[-1]
        final_rows.append(last)
        start_value = _row_value(first)
        end_value = _row_value(last)
        direction = get_direction_text(start_value, end_value)
        lines.append(
            "- "
            f"{country_label}: {first.get('year')} là {format_value(start_value, unit)}, "
            f"đến {last.get('year')} là {format_value(end_value, unit)} -> {direction}."
        )

    highest, lowest = _best_rows_by_value(final_rows)
    if highest and lowest and highest is not lowest:
        high_country = get_country_label(highest)
        low_country = get_country_label(lowest)
        if len(final_rows) == 2:
            lines.append(f"Ở cuối kỳ, {high_country} cao hơn {low_country}.")
        else:
            lines.append(f"Ở cuối kỳ, {high_country} cao nhất và {low_country} thấp nhất trong nhóm này.")

    return "\n\n".join([lines[0], "\n".join(lines[1:])])


def compose_ranking_answer(
    indicator_code: str | None,
    year: int | None,
    rows: list[dict],
    limit: int | None = None,
    order: str | None = None,
) -> str:
    label = get_indicator_label(indicator_code)
    unit = get_indicator_unit(indicator_code)
    year_text = f"năm {year}" if year is not None else "năm được chọn"

    if not rows:
        return f"Không tìm thấy dữ liệu xếp hạng cho {label} {year_text}."

    display_rows = rows[: min(len(rows), 10)]
    n = min(limit or len(display_rows), len(display_rows))
    order_text = "theo dữ liệu trả về"
    if order == "desc":
        order_text = "cao nhất"
    elif order == "asc":
        order_text = "thấp nhất"

    lines = [f"Top {n} quốc gia có {label} {order_text} {year_text}:"]
    for index, row in enumerate(display_rows[:n], start=1):
        country = get_country_label(row)
        lines.append(f"{index}. {country} - {format_value(row.get('value'), unit)}")

    top_country = get_country_label(display_rows[0])
    if order in {"asc", "desc"}:
        lines.append(f"Dựa trên dữ liệu trả về, {top_country} đứng đầu trong nhóm này.")
    else:
        lines.append(f"Dựa trên dữ liệu trả về, {top_country} là dòng đầu tiên trong nhóm này.")

    return "\n".join(lines)


def compose_coverage_answer(
    indicator_code: str | None,
    rows: list[dict],
) -> str:
    label = get_indicator_label(indicator_code)

    if not rows:
        return f"Không tìm thấy thông tin coverage cho {label}."

    if len(rows) == 1:
        row = rows[0]
        country = get_country_label(row)
        return (
            f"Dữ liệu {label} của {country} có từ {row.get('min_year')} đến {row.get('max_year')}, "
            f"gồm {row.get('observations')} quan sát."
        )

    lines = [f"Tìm thấy coverage dữ liệu {label} cho {len(rows)} quốc gia:"]
    for row in rows[:10]:
        country = get_country_label(row)
        lines.append(f"- {country}: {row.get('min_year')}-{row.get('max_year')}, {row.get('observations')} quan sát")
    return "\n".join(lines)


def compose_trend_answer(
    indicator_code: str | None,
    country_codes: list[str],
    start_year: int | None,
    end_year: int | None,
    rows: list[dict],
    is_analytics_series: bool,
) -> str:
    label = get_indicator_label(indicator_code)
    unit = get_indicator_unit(indicator_code)
    period = format_year_range(start_year, end_year)

    if not rows:
        return f"Không tìm thấy chuỗi thời gian phù hợp cho {label} trong {period}."

    grouped = _group_rows_by_country(rows)
    country_text = f" của {grouped[0][0]}" if len(grouped) == 1 else ""
    lines = [f"Xu hướng {label}{country_text} giai đoạn {period}:"]

    for country_label, items in grouped[:5]:
        numeric_items = [row for row in items if safe_number(_row_value(row)) is not None]
        if not numeric_items:
            lines.append(f"- {country_label}: chưa đủ dữ liệu số để tóm tắt.")
            continue

        first = numeric_items[0]
        last = numeric_items[-1]
        highest, lowest = _best_rows_by_value(numeric_items)
        direction = get_direction_text(_row_value(first), _row_value(last))

        if len(grouped) == 1:
            lines.append(f"- Đầu kỳ {first.get('year')}: {format_value(_row_value(first), unit)}")
            lines.append(f"- Cuối kỳ {last.get('year')}: {format_value(_row_value(last), unit)}")
            lines.append(f"- Xu hướng chung: {direction}")
            if highest:
                lines.append(f"- Mức cao nhất trong dữ liệu: {format_value(_row_value(highest), unit)} vào năm {highest.get('year')}")
            if lowest:
                lines.append(f"- Mức thấp nhất trong dữ liệu: {format_value(_row_value(lowest), unit)} vào năm {lowest.get('year')}")
        else:
            lines.append(
                "- "
                f"{country_label}: {first.get('year')} là {format_value(_row_value(first), unit)}, "
                f"đến {last.get('year')} là {format_value(_row_value(last), unit)} -> {direction}."
            )

    if is_analytics_series:
        lines.append("Giá trị thực tế được dùng làm số chính; xu hướng là đường ước tính từ dữ liệu.")

    return "\n".join(lines)


def compose_anomaly_answer(
    indicator_code: str | None,
    country_codes: list[str],
    start_year: int | None,
    end_year: int | None,
    rows: list[dict],
    threshold: float = 0.75,
) -> str:
    label = get_indicator_label(indicator_code)
    unit = get_indicator_unit(indicator_code)
    period = format_year_range(start_year, end_year)

    if not rows:
        return f"Không tìm thấy điểm bất thường rõ ràng cho {label} trong {period} với ngưỡng anomaly_score >= {threshold}."

    lines = [f"Các điểm bất thường đáng chú ý của {label}:"]
    for index, row in enumerate(rows[:10], start=1):
        country = get_country_label(row)
        actual = format_value(row.get("actual_value"), unit)
        trend = format_value(row.get("trend_value"), unit)
        score = format_value(row.get("anomaly_score"))
        lines.append(
            f"{index}. {country}, {row.get('year')}: thực tế {actual}, "
            f"xu hướng ước tính {trend}, anomaly_score {score}."
        )

    lines.append("Các điểm này cho thấy độ lệch so với xu hướng trong dữ liệu, không tự động chứng minh nguyên nhân.")
    return "\n".join(lines)


def compose_fallback_answer(payload: dict[str, Any]) -> str:
    return (
        "Hiện hệ thống chưa có mẫu trả lời phù hợp cho dạng yêu cầu này. "
        "Bạn có thể hỏi lại bằng cách nêu rõ chỉ số, quốc gia và giai đoạn cần phân tích."
    )


def strip_internal_terms(text: str) -> str:
    text = replace_indicator_codes(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
