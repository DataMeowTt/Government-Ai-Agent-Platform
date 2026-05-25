from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from warehouse.bigquery_warehouse_rebuild import (
    build_analytics_tables,
    build_gold_tables,
    build_publish_plan,
    derive_runtime_metadata,
    run_silver_preflight,
)
import warehouse.bigquery_warehouse_rebuild as warehouse_rebuild
from warehouse.bigquery_warehouse_validation import load_table_contract
from jobs.rebuild_bigquery_warehouse import parse_args as parse_rebuild_args


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


class _StubExecutor:
    def __init__(self, row_count: int) -> None:
        self._row_count = row_count

    def table_exists(self, _table_id: str) -> bool:
        return True

    def query_dataframe(self, query: str, *, max_bytes_billed: int | None = None) -> pd.DataFrame:
        del max_bytes_billed
        if "INFORMATION_SCHEMA.COLUMNS" in query:
            rows = []
            for col in (
                "country_code",
                "country",
                "year",
                "indicator",
                "value",
                "source",
                "run_id",
                "run_date",
                "loaded_at",
            ):
                rows.append({"column_name": col, "is_nullable": "NO", "data_type": "STRING"})
            return pd.DataFrame(rows)
        if "SUM(CASE WHEN" in query:
            return pd.DataFrame([{"country_code": 0, "country": 0, "year": 0, "indicator": 0, "source": 0, "run_id": 0, "run_date": 0, "loaded_at": 0}])
        if "GROUP BY source" in query:
            return pd.DataFrame([{"source": "wdi", "row_count": self._row_count}])
        if "MIN(year)" in query:
            return pd.DataFrame([{"year_min": 2000, "year_max": 2025, "country_count": 1, "indicator_count": 1}])
        raise AssertionError(f"Unexpected query: {query}")

    def query_scalar_int(self, query: str, *, max_bytes_billed: int | None = None) -> int:
        del query, max_bytes_billed
        return self._row_count


def test_dynamic_validation_accepts_non_historical_row_count() -> None:
    preflight = run_silver_preflight(
        executor=_StubExecutor(123456),
        silver_table_id="western-pivot-452008-a6.gov_ai_silver.silver_indicators",
        expected_row_count=None,
    )
    assert preflight["row_count"] == 123456
    assert preflight["dynamic_row_count_validation"] is True


def test_explicit_expected_row_count_still_fails_on_mismatch() -> None:
    with pytest.raises(ValueError, match="Silver row_count mismatch"):
        run_silver_preflight(
            executor=_StubExecutor(10),
            silver_table_id="western-pivot-452008-a6.gov_ai_silver.silver_indicators",
            expected_row_count=11,
        )


def test_rebuild_cli_defaults_to_dynamic_validation() -> None:
    args = parse_rebuild_args([])
    assert args.expected_silver_row_count is None


def test_indicator_contract_fallback_when_analytics_worker_not_packaged(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    contract = warehouse_rebuild._load_indicator_contract_module(repo_root)

    assert "gold_growth_dynamics" in contract.TABLES_INDICATORS
    assert "GFCF_to_GDP" in contract.INDICATORS_FOR_CLUSTER
    assert contract.PUBLIC_INDICATORS["urban_pop_pct"]["gold_table"] == "gold_social_welfare"


def test_rebuild_get_active_project_falls_back_to_runtime_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROJECT_ID", "western-pivot-452008-a6")
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GCLOUD_PROJECT", raising=False)
    monkeypatch.setattr("warehouse.bigquery_warehouse_rebuild.shutil.which", lambda _name: None)

    assert warehouse_rebuild.get_active_gcloud_project() == "western-pivot-452008-a6"
