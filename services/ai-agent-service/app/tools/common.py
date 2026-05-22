from decimal import Decimal
from typing import Any

from app.catalog.indicator_catalog import IndicatorMeta, get_indicator
from app.catalog.canonical_indicator_catalog import (
    CanonicalIndicator,
    get_indicator as get_canonical_indicator,
)
from app.core.config import settings


class ToolError(Exception):
    pass


def use_bigquery_data_source() -> bool:
    return settings.ai_agent_data_source.lower() == "bigquery"


def require_indicator(indicator_code: str) -> IndicatorMeta:
    indicator = get_indicator(indicator_code)

    if not indicator:
        raise ToolError(f"Unsupported indicator: {indicator_code}")

    return indicator


def require_canonical_indicator(indicator_code: str) -> CanonicalIndicator:
    indicator = get_canonical_indicator(indicator_code)
    if not indicator:
        raise ToolError(f"Unsupported indicator: {indicator_code}")
    return indicator


def require_family_support(indicator_code: str, family: str) -> CanonicalIndicator:
    indicator = require_canonical_indicator(indicator_code)
    support_flag = f"supports_{family}"
    if not getattr(indicator, support_flag, False):
        raise ToolError(f"Indicator {indicator_code} does not support family {family}")
    return indicator


def quote_identifier(identifier: str) -> str:
    safe = identifier.replace('"', '""')
    return f'"{safe}"'


def indicator_column_name(indicator) -> str:
    return getattr(indicator, "gold_column", None) or indicator.code


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
