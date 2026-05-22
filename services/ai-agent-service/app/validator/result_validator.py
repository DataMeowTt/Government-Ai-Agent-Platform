from dataclasses import asdict
from typing import Any

from app.pipeline.schemas import ResultValidation
from app.resolver.country_resolver import COUNTRIES


def validate_tool_result(
    rows: list[dict],
    validated_query: dict[str, Any],
) -> ResultValidation:
    safe_rows = rows if isinstance(rows, list) else []

    intent = str(validated_query.get("intent") or "")
    requested_countries = _string_list(validated_query.get("countries"))

    numeric_rows = _numeric_rows_for_intent(safe_rows, intent)
    if intent == "COVERAGE":
        country_rows = safe_rows
    else:
        country_rows = numeric_rows
    available_countries = _available_countries(country_rows)

    check_missing_countries = intent in {
        "COMPARE_COUNTRIES",
        "TIME_SERIES",
        "TREND_ANALYSIS",
        "VALUE_LOOKUP",
        "ANOMALY_DETECTION",
        "COVERAGE",
    }

    is_anomaly_empty = intent == "ANOMALY_DETECTION" and not safe_rows
    missing_countries = [] if is_anomaly_empty else (
        [code for code in requested_countries if code not in available_countries]
        if check_missing_countries
        else []
    )

    years = _row_years(numeric_rows)
    actual_min_year = min(years) if years else None
    actual_max_year = max(years) if years else None

    requested_start_year = validated_query.get("effective_start_year")
    requested_end_year = validated_query.get("effective_end_year")

    warnings: list[str] = []
    empty_result_kind = None

    if is_anomaly_empty:
        empty_result_kind = "no_anomaly_detected"
        warnings.append("Không phát hiện điểm bất thường vượt ngưỡng trong giai đoạn được yêu cầu.")
    elif not safe_rows:
        empty_result_kind = "no_data"
        warnings.append("Không tìm thấy dữ liệu phù hợp cho yêu cầu này.")

    for country_code in missing_countries:
        country_label = _country_label(country_code)
        warnings.append(f"Không tìm thấy dữ liệu phù hợp cho {country_label} trong giai đoạn được yêu cầu.")

    if (
        actual_min_year is not None
        and requested_start_year is not None
        and actual_min_year > int(requested_start_year)
    ):
        warnings.append(f"Dữ liệu hiện có trong kết quả bắt đầu từ năm {actual_min_year}, muộn hơn năm yêu cầu {requested_start_year}.")

    if (
        actual_max_year is not None
        and requested_end_year is not None
        and actual_max_year < int(requested_end_year)
    ):
        warnings.append(f"Dữ liệu hiện có trong kết quả đến năm {actual_max_year}, sớm hơn năm yêu cầu {requested_end_year}.")

    return ResultValidation(
        row_count=len(safe_rows),
        requested_countries=requested_countries,
        available_countries=available_countries,
        missing_countries=missing_countries,
        requested_start_year=int(requested_start_year) if requested_start_year is not None else None,
        requested_end_year=int(requested_end_year) if requested_end_year is not None else None,
        actual_min_year=actual_min_year,
        actual_max_year=actual_max_year,
        actual_start_year=actual_min_year,
        actual_end_year=actual_max_year,
        empty_result_kind=empty_result_kind,
        has_numeric_rows=bool(numeric_rows),
        is_empty=len(safe_rows) == 0,
        is_partial=bool(missing_countries),
        warnings=_dedupe(warnings),
    )


def result_validation_to_dict(rv: ResultValidation) -> dict:
    return asdict(rv)


def _string_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).upper().strip() for item in value if str(item or "").strip()]
    return [str(value).upper().strip()]


def _available_countries(rows: list[dict]) -> list[str]:
    countries: list[str] = []
    for row in rows:
        code = row.get("country_code")
        if code is None:
            continue
        text = str(code).upper().strip()
        if text and text not in countries:
            countries.append(text)
    return countries


def _row_years(rows: list[dict]) -> list[int]:
    years: list[int] = []
    for row in rows:
        try:
            years.append(int(row.get("year")))
        except (TypeError, ValueError):
            continue
    return years


def _numeric_rows_for_intent(rows: list[dict], intent: str) -> list[dict]:
    numeric_rows: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if intent == "COVERAGE":
            if _safe_number(row.get("observations")) is not None:
                numeric_rows.append(row)
            continue
        if intent == "ANOMALY_DETECTION":
            if _safe_number(row.get("actual_value")) is not None or _safe_number(row.get("anomaly_score")) is not None:
                numeric_rows.append(row)
            continue
        if _safe_number(row.get("value")) is not None or _safe_number(row.get("actual_value")) is not None:
            numeric_rows.append(row)
    return numeric_rows


def _safe_number(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _country_label(country_code: str) -> str:
    country = COUNTRIES.get(str(country_code).upper())
    return country.name if country else str(country_code)


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result
