from __future__ import annotations

from decimal import Decimal
import math
import re
from typing import Any


INDICATOR_LABELS: dict[str, str] = {
    "govdebt_GDP": "nợ công/GDP",
    "inflation_cpi": "lạm phát CPI",
    "inflation_deflator": "lạm phát GDP deflator",
    "inflation_gap": "chênh lệch lạm phát CPI và deflator",
    "unemployment_total": "tỷ lệ thất nghiệp",
    "unemployment_youth": "tỷ lệ thất nghiệp thanh niên",
    "youth_unemployment_gap": "chênh lệch thất nghiệp thanh niên",
    "rGDP_growth_YoY": "tăng trưởng GDP thực",
    "GDP_growth_YoY": "tăng trưởng GDP danh nghĩa",
    "GDP_growth_trend_5yr": "xu hướng tăng trưởng GDP 5 năm",
    "GDP_pc_growth_gap": "chênh lệch tăng trưởng GDP bình quân đầu người",
    "log_rGDP_pc_USD": "log GDP thực bình quân đầu người",
    "GDP_per_capita": "GDP bình quân đầu người",
    "tax_revenue_pct_GDP": "thu thuế/GDP",
    "fiscal_balance_GDP": "cán cân ngân sách/GDP",
    "govrev_GDP": "thu ngân sách/GDP",
    "govexp_GDP": "chi ngân sách/GDP",
    "real_interest_rate": "lãi suất thực",
    "ltrate": "lãi suất dài hạn",
    "GFCF_to_GDP": "đầu tư cố định gộp/GDP",
    "GNI_to_GDP": "GNI/GDP",
    "poverty_headcount": "tỷ lệ nghèo",
    "poverty_change_5yr": "thay đổi tỷ lệ nghèo 5 năm",
    "hcons_growth": "tăng trưởng tiêu dùng hộ gia đình",
    "hcons_share": "tiêu dùng hộ gia đình/GDP",
    "REER_deviation": "độ lệch REER",
    "spending_efficiency": "hiệu quả chi tiêu công",
    "agri_va_share": "tỷ trọng nông nghiệp/GDP",
    "manuf_va_share": "tỷ trọng công nghiệp chế biến/GDP",
    "food_bev_share_manuf": "tỷ trọng thực phẩm/đồ uống trong sản xuất chế biến",
    "trade_pct_gdp": "độ mở thương mại",
    "trade_openness": "độ mở thương mại",
    "urban_pop_pct": "tỷ lệ dân số đô thị",
    "urban_pop_growth": "tăng trưởng dân số đô thị",
    "pop_density": "mật độ dân số",
    "pop_growth": "tăng trưởng dân số",
    "crisis_composite": "chỉ số tổng hợp khủng hoảng",
    "crisis_any": "có khủng hoảng",
    "SovDebtCrisis": "khủng hoảng nợ công",
    "CurrencyCrisis": "khủng hoảng tiền tệ",
    "BankingCrisis": "khủng hoảng ngân hàng",
    "rolling_mean_5yr": "tăng trưởng GDP trung bình 5 năm",
    "trend_deviation": "độ lệch xu hướng tăng trưởng",
    "debt_change_YoY": "thay đổi nợ công hằng năm",
    "cumulative_deficit_5yr": "thâm hụt tích lũy 5 năm",
    "infl": "lạm phát GDP deflator",
    "rolling_3yr_avg_cpi": "lạm phát CPI trung bình 3 năm",
    "youth_gap_ratio": "tỷ lệ thất nghiệp thanh niên so với tổng thể",
    "self_employed_pct": "tỷ lệ lao động tự doanh",
    "log_pop_density": "mật độ dân số",
    "GDP_value": "GDP",
    "GFCF_value": "đầu tư cố định gộp",
    "GNI_value": "GNI",
    "Agri_VA": "giá trị gia tăng nông nghiệp",
    "Manuf_VA": "giá trị gia tăng công nghiệp chế biến",
    "VA_FoodBev": "giá trị gia tăng thực phẩm/đồ uống",
}


PERCENT_INDICATORS = {
    "govdebt_GDP",
    "inflation_cpi",
    "inflation_deflator",
    "inflation_gap",
    "unemployment_total",
    "unemployment_youth",
    "youth_unemployment_gap",
    "rGDP_growth_YoY",
    "GDP_growth_YoY",
    "GDP_growth_trend_5yr",
    "GDP_pc_growth_gap",
    "tax_revenue_pct_GDP",
    "fiscal_balance_GDP",
    "govrev_GDP",
    "govexp_GDP",
    "real_interest_rate",
    "ltrate",
    "GFCF_to_GDP",
    "poverty_headcount",
    "poverty_change_5yr",
    "hcons_growth",
    "hcons_share",
    "REER_deviation",
    "agri_va_share",
    "manuf_va_share",
    "food_bev_share_manuf",
    "trade_pct_gdp",
    "urban_pop_pct",
    "urban_pop_growth",
    "pop_growth",
    "rolling_mean_5yr",
    "trend_deviation",
    "debt_change_YoY",
    "cumulative_deficit_5yr",
    "infl",
    "rolling_3yr_avg_cpi",
    "youth_gap_ratio",
    "self_employed_pct",
}


INDICATOR_UNITS: dict[str, str] = {
    **{code: "%" for code in PERCENT_INDICATORS},
    "GNI_to_GDP": "tỷ lệ",
    "spending_efficiency": "tỷ lệ",
    "pop_density": "người/km²",
    "log_pop_density": "log",
    "log_rGDP_pc_USD": "log",
    "crisis_any": "0/1",
    "SovDebtCrisis": "0/1",
    "CurrencyCrisis": "0/1",
    "BankingCrisis": "0/1",
    "crisis_composite": "0-3",
}


def get_indicator_label(indicator_code: str | None) -> str:
    if not indicator_code:
        return "chỉ số"
    return INDICATOR_LABELS.get(indicator_code, indicator_code.replace("_", " "))


def get_indicator_unit(indicator_code: str | None) -> str:
    if not indicator_code:
        return ""
    if indicator_code in INDICATOR_UNITS:
        return INDICATOR_UNITS[indicator_code]
    if indicator_code.startswith("log_"):
        return "log"
    return ""


def get_country_label(row: dict | None = None, country_code: str | None = None) -> str:
    row = row or {}
    for key in ("country", "country_name", "country_code"):
        value = row.get(key)
        if value:
            return str(value)
    if country_code:
        return str(country_code)
    return "quốc gia không xác định"


def safe_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        value = float(value)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def format_value(value: Any, unit: str | None = None) -> str:
    if value is None:
        return "không có dữ liệu"

    text = str(value).strip()
    number = safe_number(value)
    if number is None:
        return text or "không có dữ liệu"

    if abs(number) < 0.005:
        number = 0.0
    if number.is_integer():
        formatted = f"{int(number)}"
    else:
        formatted = f"{number:.2f}".rstrip("0").rstrip(".")

    normalized_unit = (unit or "").strip()
    if not normalized_unit or normalized_unit in {"0/1", "0-3"}:
        return formatted
    if normalized_unit == "%":
        return formatted if formatted.endswith("%") else f"{formatted}%"
    if normalized_unit == "log":
        return f"{formatted} (log)"
    return f"{formatted} {normalized_unit}"


def format_year_range(start_year: int | None, end_year: int | None) -> str:
    if start_year is not None and end_year is not None:
        if start_year == end_year:
            return f"năm {start_year}"
        return f"{start_year}-{end_year}"
    if start_year is not None:
        return f"từ năm {start_year}"
    if end_year is not None:
        return f"đến năm {end_year}"
    return "giai đoạn được chọn"


def get_direction_text(start_value: Any, end_value: Any) -> str:
    start_number = safe_number(start_value)
    end_number = safe_number(end_value)
    if start_number is None or end_number is None:
        return "chưa đủ dữ liệu để xác định xu hướng"

    delta = end_number - start_number
    tolerance = max(abs(start_number), abs(end_number), 1.0) * 0.005
    if abs(delta) <= tolerance:
        return "gần như không đổi"
    return "tăng" if delta > 0 else "giảm"


def replace_indicator_codes(text: str) -> str:
    output = text
    for code, label in sorted(INDICATOR_LABELS.items(), key=lambda item: len(item[0]), reverse=True):
        output = re.sub(
            rf"(?<![A-Za-z0-9_]){re.escape(code)}(?![A-Za-z0-9_])",
            label,
            output,
            flags=re.IGNORECASE,
        )
    return output


INTERNAL_TERM_REPLACEMENTS: dict[str, str] = {
    "Gemini Router": "trợ lý",
    "AI Agent Service": "dịch vụ dữ liệu",
    "AI Agent": "trợ lý",
    "parsedQuery": "diễn giải yêu cầu",
    "query planner": "tiến trình xử lý",
    "model parser": "tiến trình xử lý",
    "database": "dữ liệu",
    "DB": "dữ liệu",
    "ngrok": "kết nối",
    "Kaggle": "môi trường xử lý",
    "router": "tiến trình xử lý",
    "parser": "tiến trình xử lý",
    "tool": "công cụ xử lý",
}


TECHNICAL_ANSWER_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"Đã\s+query\s+dữ\s+liệu\s+thật[^.。!?\n]*(?:[.。!?]\s*)?", ""),
    (r"Đã\s+so\s+sánh\s+dữ\s+liệu\s+thật[^.。!?\n]*(?:[.。!?]\s*)?", ""),
    (r"Tìm\s+thấy\s+\d+\s+dòng\s+dữ\s+liệu[^.。!?\n]*(?:[.。!?]\s*)?", ""),
    (r"Da\s+query\s+du\s+lieu\s+that[^.。!?\n]*(?:[.。!?]\s*)?", ""),
    (r"Da\s+so\s+sanh\s+du\s+lieu\s+that[^.。!?\n]*(?:[.。!?]\s*)?", ""),
    (r"Tim\s+thay\s+\d+\s+dong\s+du\s+lieu[^.。!?\n]*(?:[.。!?]\s*)?", ""),
)


def sanitize_user_facing_text(text: str) -> str:
    output = replace_indicator_codes(str(text or ""))

    for pattern, replacement in TECHNICAL_ANSWER_PATTERNS:
        output = re.sub(pattern, replacement, output, flags=re.IGNORECASE)

    for old, new in sorted(INTERNAL_TERM_REPLACEMENTS.items(), key=lambda item: len(item[0]), reverse=True):
        output = re.sub(
            rf"(?<![A-Za-z0-9_]){re.escape(old)}(?![A-Za-z0-9_])",
            new,
            output,
            flags=re.IGNORECASE,
        )

    output = re.sub(r"[ \t]+", " ", output)
    output = re.sub(r"\s*\n\s*", "\n", output)
    output = re.sub(r"\n{3,}", "\n\n", output)
    return output.strip()
