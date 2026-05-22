import sys
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))


from app.catalog.canonical_indicator_catalog import (  # noqa: E402
    detect_unsupported_indicator,
    get_indicator,
    get_indicator_analytics_metadata,
    get_supported_indicators_compact,
    list_indicator_codes,
    resolve_indicator_alias,
)
from app.catalog.country_group_catalog import (  # noqa: E402
    expand_country_groups,
    resolve_country_group,
)


def _assert_resolves(alias: str, expected_code: str) -> None:
    match = resolve_indicator_alias(alias)
    assert match is not None, alias
    assert match.indicator.code == expected_code, (alias, match.indicator.code)


def main() -> None:
    _assert_resolves("GDP per capita", "log_rGDP_pc_USD")
    _assert_resolves("GDP bình quân đầu người", "log_rGDP_pc_USD")
    _assert_resolves("trade openness", "trade_pct_gdp")
    _assert_resolves("trade_open_pct_gdp", "trade_pct_gdp")
    _assert_resolves("nợ công", "govdebt_GDP")
    _assert_resolves("thất nghiệp", "unemployment_total")
    _assert_resolves("lạm phát CPI", "inflation_cpi")

    assert detect_unsupported_indicator("current account/GDP") is not None
    assert detect_unsupported_indicator("external debt/GNI") is not None
    assert detect_unsupported_indicator("trade_open_pct_gdp") is None

    assert get_indicator("current_account_GDP") is None
    assert get_indicator("external_debt_GNI") is None
    assert get_indicator("trade_pct_gdp").gold_table == "gold_social_welfare"
    assert get_indicator("log_rGDP_pc_USD").gold_table == "gold_growth_dynamics"

    assert get_indicator_analytics_metadata("govdebt_GDP")["supports_anomaly"] is True
    assert get_indicator_analytics_metadata("trade_pct_gdp")["supports_anomaly"] is False

    group_match = resolve_country_group("ASEAN")
    assert group_match is not None
    assert group_match.group.code == "ASEAN"

    expanded_asean = expand_country_groups(["ASEAN"])
    for country_code in ("VNM", "THA", "IDN", "MYS", "PHL"):
        assert country_code in expanded_asean

    compact_catalog = get_supported_indicators_compact()
    assert compact_catalog
    assert all("description_vi" in item for item in compact_catalog)

    indicator_codes = list_indicator_codes()
    assert "current_account_GDP" not in indicator_codes
    assert "external_debt_GNI" not in indicator_codes

    print("canonical catalog checks passed")


if __name__ == "__main__":
    main()
