from __future__ import annotations

from pathlib import Path

import pandas as pd

from warehouse.bigquery_warehouse_rebuild import (
    build_analytics_tables,
    build_gold_tables,
    build_publish_plan,
    derive_runtime_metadata,
)
from warehouse.bigquery_warehouse_validation import load_table_contract


def _make_silver_fixture() -> pd.DataFrame:
    indicators = [
        "income_group_encoded",
        "development_group",
        "rgdp_growth_yoy",
        "rolling_mean_5yr",
        "gdp_growth_yoy",
        "gdp_growth_trend_5yr",
        "trend_deviation",
        "gdp_pc_growth_gap",
        "log_rgdp_pc_usd",
        "govdebt_gdp",
        "debt_change_yoy",
        "govrev_gdp",
        "govexp_gdp",
        "fiscal_balance_gdp",
        "cumulative_deficit_5yr",
        "ltrate",
        "infl",
        "real_interest_rate",
        "tax_revenue_gdp",
        "inflation_consumer_prices",
        "inflation_gdp_deflator",
        "inflation_gap",
        "rolling_3yr_avg_cpi",
        "sov_debt_crisis",
        "currency_crisis",
        "banking_crisis",
        "crisis_composite",
        "crisis_any",
        "reer_deviation",
        "spending_efficiency",
        "unemployment_total",
        "unemployment_youth",
        "youth_unemployment_gap",
        "youth_gap_ratio",
        "self_employed_total",
        "poverty_headcount_ratio",
        "poverty_change_5yr",
        "urban_population",
        "urban_population_growth",
        "population_density",
        "log_pop_density",
        "population_growth",
        "hcons_gdp",
        "hcons_growth",
        "trade_gdp",
        "decade",
        "gdp_value",
        "gfcf_value",
        "gni_value",
        "agri_va",
        "manuf_va",
        "va_foodbev",
        "gfcf_to_gdp",
        "gni_to_gdp",
        "agri_va_share",
        "manuf_va_share",
        "food_bev_share_manuf",
        "flag_score",
    ]

    rows = []
    for country_code, country_name, offset in (("VNM", "Viet Nam", 0.0), ("THA", "Thailand", 1.0)):
        for year in (2000, 2010, 2020):
            base = float(year - 1990) + offset
            for indicator in indicators:
                if indicator == "income_group_encoded":
                    value = 2.0
                elif indicator == "development_group":
                    value = 1.0
                elif indicator in {"sov_debt_crisis", "currency_crisis", "banking_crisis", "crisis_any"}:
                    value = 0.0 if year < 2020 else 1.0
                elif indicator == "crisis_composite":
                    value = 0.0 if year < 2020 else 2.0
                elif indicator == "decade":
                    value = float(year)
                elif indicator == "flag_score":
                    value = 1.0
                else:
                    value = base
                rows.append(
                    {
                        "country_code": country_code,
                        "country": country_name,
                        "year": year,
                        "indicator": indicator,
                        "value": value,
                        "source": "wdi",
                        "run_id": "run-fixture",
                        "run_date": pd.to_datetime("2026-05-18").date(),
                        "loaded_at": pd.Timestamp("2026-05-18T00:00:00"),
                    }
                )
    return pd.DataFrame(rows)


def test_build_gold_and_analytics_tables(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    contract = load_table_contract(repo_root / "contracts" / "table_contract.yaml")
    silver_df = _make_silver_fixture()
    metadata = derive_runtime_metadata(silver_df)

    gold_tables, gold_summary = build_gold_tables(
        silver_df=silver_df,
        metadata=metadata,
        contract=contract,
        output_dir=tmp_path,
    )
    assert len(gold_tables) == 5
    assert len(gold_summary) == 5
    assert all(item["row_count"] > 0 for item in gold_summary)

    analytics_tables, analytics_summary = build_analytics_tables(
        repo_root=repo_root,
        gold_tables=gold_tables,
        metadata=metadata,
        contract=contract,
        output_dir=tmp_path,
    )
    assert "analytics_clusters" in analytics_tables
    assert analytics_tables["analytics_clusters"].shape[0] > 0
    assert any(item["table_name"] == "analytics_clusters" for item in analytics_summary)

    publish_plan = build_publish_plan(
        metadata=metadata,
        gold_tables=gold_tables,
        analytics_tables=analytics_tables,
        project_id="western-pivot-452008-a6",
    )
    assert publish_plan["write_strategy"] == "staging_validate_write_truncate"
    assert len(publish_plan["tables"]) == 11

