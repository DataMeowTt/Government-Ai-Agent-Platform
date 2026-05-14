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
    sanitize_user_facing_text,
)
from app.resolver.country_resolver import COUNTRIES


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
    highest = max(numeric_rows, key=lambda row: safe_number(_row_value(row)))
    lowest = min(numeric_rows, key=lambda row: safe_number(_row_value(row)))
    return highest, lowest


def _numeric_rows(items: list[dict]) -> list[dict]:
    return [
        row
        for row in items
        if isinstance(row, dict)
        and safe_number(_row_value(row)) is not None
        and _row_year(row) is not None
    ]


def _actual_period_from_rows(rows: list[dict]) -> tuple[int | None, int | None]:
    years = [_row_year(row) for row in _numeric_rows(rows)]
    years = [year for year in years if year is not None]
    if not years:
        return None, None
    return min(years), max(years)


def _period_gap_warning(result_validation: dict[str, Any] | None) -> str | None:
    if not isinstance(result_validation, dict):
        return None
    requested_end = result_validation.get("requested_end_year")
    actual_end = result_validation.get("actual_end_year") or result_validation.get("actual_max_year")
    if requested_end is not None and actual_end is not None and int(actual_end) < int(requested_end):
        return f"Dữ liệu hiện có trong kết quả đến năm {actual_end}, sớm hơn năm yêu cầu {requested_end}."
    requested_start = result_validation.get("requested_start_year")
    actual_start = result_validation.get("actual_start_year") or result_validation.get("actual_min_year")
    if requested_start is not None and actual_start is not None and int(actual_start) > int(requested_start):
        return f"Dữ liệu hiện có trong kết quả bắt đầu từ năm {actual_start}, muộn hơn năm yêu cầu {requested_start}."
    return None


def _dedupe_warning_texts(warnings: list[str]) -> list[str]:
    cleaned: list[str] = []
    semantic_seen: set[str] = set()
    for warning in warnings:
        text = sanitize_user_facing_text(str(warning or "").strip())
        if not text:
            continue
        lowered = text.lower()
        key = lowered
        if "không tìm thấy dữ liệu phù hợp" in lowered or "không có dữ liệu phù hợp" in lowered:
            key = "no_data"
        if key in semantic_seen:
            continue
        semantic_seen.add(key)
        cleaned.append(text)
    return cleaned


def compose_off_topic_answer() -> str:
    return (
        "Câu hỏi này nằm ngoài phạm vi dữ liệu chỉ số kinh tế, xã hội và quản trị hiện có. "
        "Bạn có thể hỏi về GDP, nợ công, lạm phát, thất nghiệp, nghèo đói, khủng hoảng, "
        "dân số, đô thị hóa, đầu tư hoặc thương mại."
    )


CLARIFICATION_FALLBACK = "Bạn có thể nói rõ chỉ số, quốc gia và giai đoạn muốn phân tích không?"


def sanitize_clarification_questions(questions: list[str] | None) -> list[str]:
    sanitized: list[str] = []
    for question in questions or []:
        text = sanitize_user_facing_text(str(question or "").strip())
        lowered = text.lower()

        if not text:
            continue
        if (
            "please clarify" in lowered
            or "missing or ambiguous slot" in lowered
            or "need clarification" in lowered
            or "chua xac dinh" in lowered
            or "chưa xác định" in lowered
        ):
            if "indicator" in lowered or "chỉ số" in lowered:
                text = "Bạn muốn phân tích chỉ số nào? Ví dụ: nợ công/GDP, lạm phát CPI, tỷ lệ thất nghiệp, tăng trưởng GDP thực."
            elif "country" in lowered or "countries" in lowered or "quốc gia" in lowered:
                text = "Bạn muốn xem cho quốc gia hoặc nhóm quốc gia nào?"
            elif "time" in lowered or "year" in lowered or "period" in lowered or "năm" in lowered or "giai đoạn" in lowered:
                text = "Bạn muốn xem năm hoặc giai đoạn nào?"
            else:
                text = "Bạn có thể nói rõ chỉ số, quốc gia và giai đoạn muốn phân tích không?"
        elif "which indicator" in lowered or "compare or analyze which indicator" in lowered:
            text = "Bạn muốn phân tích chỉ số nào? Ví dụ: nợ công/GDP, lạm phát CPI, tỷ lệ thất nghiệp, tăng trưởng GDP thực."
        elif "missing indicator" in lowered:
            text = "Bạn muốn phân tích chỉ số nào? Ví dụ: nợ công/GDP, lạm phát CPI, tỷ lệ thất nghiệp, tăng trưởng GDP thực."
        elif "missing country" in lowered or ("please specify" in lowered and ("country" in lowered or "countries" in lowered)):
            text = "Bạn muốn xem cho quốc gia hoặc nhóm quốc gia nào?"
        elif "missing time" in lowered or "missing year" in lowered or ("please specify" in lowered and ("time" in lowered or "year" in lowered or "period" in lowered)):
            text = "Bạn muốn xem năm hoặc giai đoạn nào?"
        elif "please specify" in lowered:
            text = "Bạn có thể nói rõ chỉ số, quốc gia và giai đoạn muốn phân tích không?"
        elif "indicator" in lowered and "chỉ số" not in lowered:
            text = "Bạn muốn phân tích chỉ số nào? Ví dụ: nợ công/GDP, lạm phát CPI, tỷ lệ thất nghiệp, tăng trưởng GDP thực."
        elif "country" in lowered and "quốc gia" not in lowered:
            text = "Bạn muốn xem cho quốc gia hoặc nhóm quốc gia nào?"
        elif ("year" in lowered or "period" in lowered or "time" in lowered) and not any(token in lowered for token in ("năm", "giai đoạn")):
            text = "Bạn muốn xem năm hoặc giai đoạn nào?"

        cleaned = sanitize_user_facing_text(text)
        if cleaned and cleaned not in sanitized:
            sanitized.append(cleaned)

    return sanitized or [CLARIFICATION_FALLBACK]


def compose_need_clarification_answer(questions: list[str] | None) -> str:
    cleaned = sanitize_clarification_questions(questions)
    if not cleaned:
        return CLARIFICATION_FALLBACK
    return sanitize_user_facing_text("Mình cần bạn làm rõ thêm: " + " ".join(cleaned))


def _sanitize_warning(text: str) -> str | None:
    raw_text = str(text or "").strip()
    text = sanitize_user_facing_text(raw_text)
    if not text:
        return None

    lowered = text.lower()
    unsupported_match = re.search(
        r"(?:unsupported indicator|indicator)\s+([A-Za-z0-9_./%-]+)\s+(?:chưa|is|not|không)",
        raw_text,
        flags=re.IGNORECASE,
    )
    if unsupported_match:
        label = replace_indicator_codes(unsupported_match.group(1))
        return f"Hiện hệ thống chưa có chỉ số {label} trong dữ liệu hiện có."
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

    prefix = "Chỉ số này chưa có trong dữ liệu hiện tại hoặc chưa được hỗ trợ."
    if cleaned and not any("chỉ số" in warning.lower() or "indicator" in warning.lower() for warning in cleaned):
        prefix = " ".join(cleaned)

    return sanitize_user_facing_text(
        f"{prefix} Bạn có thể chọn một chỉ số trong danh mục hiện có như nợ công/GDP, "
        "lạm phát CPI, tỷ lệ thất nghiệp, tăng trưởng GDP thực, thương mại/GDP, "
        "thu thuế/GDP, cân đối ngân sách/GDP, đầu tư tài sản cố định/GDP, dân số, nghèo đói hoặc khủng hoảng."
    )


def compose_no_data_answer(
    validation_reason: str | None = None,
    warnings: list[str] | None = None,
    validated_query: dict[str, Any] | None = None,
) -> str:
    query = validated_query or {}
    indicator_code = query.get("indicator")
    label = get_indicator_label(indicator_code)

    start_year = query.get("start_year")
    end_year = query.get("end_year")
    period = format_year_range(start_year, end_year)

    cleaned_warnings = _dedupe_warning_texts(warnings or [])

    cleaned_reason = sanitize_user_facing_text(validation_reason or "")

    first = f"Không tìm thấy dữ liệu phù hợp cho {label} trong {period}."
    second = "Bạn có thể thử đổi quốc gia, giai đoạn hoặc dùng coverage để kiểm tra phạm vi dữ liệu hiện có."

    if cleaned_reason and "không tìm thấy dữ liệu" not in cleaned_reason.lower() and "không có dữ liệu" not in cleaned_reason.lower():
        second = cleaned_reason
    elif cleaned_warnings:
        useful_warning = next(
            (
                warning
                for warning in cleaned_warnings
                if "không tìm thấy dữ liệu" not in warning.lower() and "không có dữ liệu" not in warning.lower()
            ),
            "",
        )
        if useful_warning:
            second = useful_warning

    return sanitize_user_facing_text(f"{first} {second}")


def compose_compare_answer(
    indicator_code: str | None,
    country_codes: list[str],
    start_year: int | None,
    end_year: int | None,
    rows: list[dict],
    result_validation: dict[str, Any] | None = None,
) -> str:
    label = get_indicator_label(indicator_code)
    unit = get_indicator_unit(indicator_code)
    period = format_year_range(start_year, end_year)

    if not rows:
        return f"Không tìm thấy dữ liệu phù hợp cho {label} trong {period}."

    lines = [f"So sánh {label} giai đoạn {period}:"]
    final_rows: list[dict] = []

    for country_label, items in _group_rows_by_country(rows):
        numeric_items = sorted(_numeric_rows(items), key=lambda row: _row_year(row) or 0)
        if not numeric_items:
            continue
        first = numeric_items[0]
        last = numeric_items[-1]
        final_rows.append(last)
        start_value = _row_value(first)
        end_value = _row_value(last)
        direction = get_direction_text(start_value, end_value)
        lines.append(
            "- "
            f"{country_label}: {first.get('year')} là {format_value(start_value, unit)}, "
            f"đến {last.get('year')} là {format_value(end_value, unit)} → {direction}."
        )
        if end_year is not None and _row_year(last) is not None and int(_row_year(last) or 0) < int(end_year):
            lines.append(f"  Dữ liệu hiện có của {country_label} kết thúc ở năm {last.get('year')}.")

    missing_countries = _missing_country_labels(result_validation)
    is_partial = bool(result_validation and (result_validation.get("is_partial") or missing_countries))

    highest, lowest = _best_rows_by_value(final_rows)
    if not is_partial and highest and lowest and highest is not lowest:
        high_country = get_country_label(highest)
        low_country = get_country_label(lowest)
        if len(final_rows) == 2:
            lines.append(f"Ở cuối kỳ, {high_country} cao hơn {low_country}.")
        else:
            lines.append(f"Ở cuối kỳ, {high_country} cao nhất và {low_country} thấp nhất trong nhóm này.")
    elif is_partial and missing_countries:
        missing_text = ", ".join(missing_countries)
        lines.append(f"Do thiếu dữ liệu cho {missing_text}, hệ thống không kết luận đầy đủ cho toàn bộ nhóm yêu cầu.")

    if not final_rows:
        return f"Không tìm thấy dữ liệu số phù hợp cho {label} trong {period}."

    gap_warning = _period_gap_warning(result_validation)
    if gap_warning and gap_warning not in lines:
        lines.append(gap_warning)

    lines.append("Biểu đồ và bảng bên dưới thể hiện chi tiết theo từng năm.")
    return sanitize_user_facing_text("\n".join(lines))


def _missing_country_labels(result_validation: dict[str, Any] | None) -> list[str]:
    if not isinstance(result_validation, dict):
        return []
    labels: list[str] = []
    for code in result_validation.get("missing_countries") or []:
        text = str(code).strip()
        if not text:
            continue
        country = COUNTRIES.get(text.upper())
        label = country.name if country else text
        if label not in labels:
            labels.append(label)
    return labels


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

    n = min(limit or len(rows), len(rows), 10)
    display_rows = rows[:n]
    order_text = "theo dữ liệu trả về"
    if order == "desc":
        order_text = "cao nhất"
    elif order == "asc":
        order_text = "thấp nhất"

    lines = [f"Top {n} quốc gia có {label} {order_text} {year_text}:"]
    for index, row in enumerate(display_rows[:n], start=1):
        country = get_country_label(row)
        lines.append(f"{index}. {country} — {format_value(_row_value(row), unit)}")

    lines.append("Bảng và biểu đồ bên dưới hiển thị các kết quả được trả về.")

    return sanitize_user_facing_text("\n".join(lines))


def compose_coverage_answer(
    indicator_code: str | None,
    rows: list[dict],
) -> str:
    label = get_indicator_label(indicator_code)

    if not rows:
        return f"Không tìm thấy thông tin phạm vi dữ liệu cho {label}."

    if len(rows) == 1:
        row = rows[0]
        country = get_country_label(row)
        return (
            f"Dữ liệu {label} của {country} có từ {row.get('min_year')} đến {row.get('max_year')}, "
            f"gồm {row.get('observations')} quan sát."
        )

    years = []
    observations = 0
    for row in rows:
        try:
            if row.get("min_year") is not None:
                years.append(int(row.get("min_year")))
            if row.get("max_year") is not None:
                years.append(int(row.get("max_year")))
            observations += int(row.get("observations") or 0)
        except (TypeError, ValueError):
            continue

    summary = f"Phạm vi dữ liệu {label} có {len(rows)} quốc gia"
    if years:
        summary += f", bao phủ khoảng {min(years)}-{max(years)}"
    if observations:
        summary += f", tổng cộng {observations} quan sát"
    summary += "."

    lines = [summary]
    lines.append("Một số quốc gia tiêu biểu:")
    for row in rows[:10]:
        country = get_country_label(row)
        lines.append(f"- {country}: {row.get('min_year')}-{row.get('max_year')}, {row.get('observations')} quan sát")

    if len(rows) > 10:
        lines.append(f"Bảng bên dưới có đầy đủ {len(rows)} quốc gia được trả về.")

    return sanitize_user_facing_text("\n".join(lines))


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
    actual_start_year, actual_end_year = _actual_period_from_rows(rows)
    if actual_start_year is not None and actual_end_year is not None:
        lines.append(f"Dữ liệu thực tế trong kết quả bao phủ {actual_start_year}-{actual_end_year}.")

    for country_label, items in grouped[:5]:
        numeric_items = sorted(_numeric_rows(items), key=lambda row: _row_year(row) or 0)
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
                f"đến {last.get('year')} là {format_value(_row_value(last), unit)} → {direction}."
            )

    if is_analytics_series:
        lines.append("Giá trị thực tế là số chính; đường xu hướng là ước tính từ dữ liệu.")

    return sanitize_user_facing_text("\n".join(lines))


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
        return (
            f"Không phát hiện điểm bất thường vượt ngưỡng {threshold} cho {label} trong {period}. "
            "Điều này có nghĩa là không có điểm nào trong kết quả vượt ngưỡng bất thường, không phải là dữ liệu bị lỗi."
        )

    lines = [f"Các điểm bất thường đáng chú ý của {label}:"]
    for index, row in enumerate(rows[:10], start=1):
        country = get_country_label(row)
        actual = format_value(row.get("actual_value"), unit)
        trend = format_value(row.get("trend_value"), unit)
        residual = format_value(row.get("residual_value"), unit)
        score = format_value(row.get("anomaly_score"))
        lines.append(
            f"{index}. {country}, {row.get('year')}: thực tế {actual}, "
            f"xu hướng {trend}, độ lệch {residual}, điểm bất thường {score}."
        )

    lines.append("Các điểm này cho thấy độ lệch so với xu hướng trong dữ liệu, không tự động chứng minh nguyên nhân.")
    return sanitize_user_facing_text("\n".join(lines))


def compose_fallback_answer(payload: dict[str, Any]) -> str:
    return (
        "Hiện hệ thống chưa có mẫu trả lời phù hợp cho dạng yêu cầu này. "
        "Bạn có thể hỏi lại bằng cách nêu rõ chỉ số, quốc gia và giai đoạn cần phân tích."
    )


def strip_internal_terms(text: str) -> str:
    return sanitize_user_facing_text(text)
