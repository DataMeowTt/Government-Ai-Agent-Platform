from decimal import Decimal
from typing import Any

from app.catalog.indicator_catalog import IndicatorMeta, get_indicator


class ToolError(Exception):
    pass


def require_indicator(indicator_code: str) -> IndicatorMeta:
    indicator = get_indicator(indicator_code)

    if not indicator:
        raise ToolError(f"Unsupported indicator: {indicator_code}")

    return indicator


def quote_identifier(identifier: str) -> str:
    safe = identifier.replace('"', '""')
    return f'"{safe}"'


def normalize_country_codes(country_codes: list[str] | None) -> list[str]:
    if not country_codes:
        return []

    return [code.upper().strip() for code in country_codes if code and code.strip()]


def clean_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)

    return value


def rows_to_dicts(rows: Any) -> list[dict]:
    return [
        {key: clean_value(value) for key, value in row._mapping.items()}
        for row in rows
    ]