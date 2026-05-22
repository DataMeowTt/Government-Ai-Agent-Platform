from dataclasses import dataclass

from app.catalog.canonical_indicator_catalog import list_indicators as list_canonical_indicators


@dataclass(frozen=True)
class IndicatorMeta:
    code: str
    name: str
    category: str
    unit: str
    gold_table: str
    gold_column: str | None = None
    analytics_table: str | None = None
    description: str = ""
    aliases: tuple[str, ...] = ()


def _to_legacy_indicator(indicator) -> IndicatorMeta:
    return IndicatorMeta(
        code=indicator.code,
        name=indicator.name_en,
        category=indicator.category,
        unit=indicator.unit,
        gold_table=indicator.gold_table,
        gold_column=indicator.gold_column,
        analytics_table=indicator.analytics_table,
        description=indicator.description_vi,
        aliases=indicator.aliases,
    )


INDICATORS: dict[str, IndicatorMeta] = {
    indicator.code: _to_legacy_indicator(indicator)
    for indicator in list_canonical_indicators()
}


def get_indicator(code: str) -> IndicatorMeta | None:
    return INDICATORS.get(code)


def list_indicators() -> list[IndicatorMeta]:
    return list(INDICATORS.values())


def list_indicator_codes() -> list[str]:
    return list(INDICATORS.keys())
