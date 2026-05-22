from __future__ import annotations

import pytest

from app.core.config import settings
from app.tools.anomaly_tool import get_indicator_anomalies
from app.tools.bigquery_tooling import execute_bigquery_select
from app.tools.common import ToolError
from app.tools.compare_tool import compare_countries
from app.tools.indicator_series_tool import get_indicator_series
from app.tools.ranking_tool import rank_countries


def _table_fqdn(dataset: str, table: str) -> str:
    return f"{settings.bigquery_project_id}.{dataset}.{table}"


def test_compare_raw_builds_safe_bigquery_sql(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_agent_data_source", "bigquery")
    calls: list[dict] = []

    def fake_run(query: str, params: dict) -> list[dict]:
        calls.append({"query": query, "params": params})
        return []

    monkeypatch.setattr("app.tools.bigquery_tooling.run_bigquery_query", fake_run)

    compare_countries(
        indicator_code="govdebt_GDP",
        country_codes=["VNM", "THA"],
        start_year=2010,
        end_year=2023,
    )

    assert len(calls) >= 1
    series_call = calls[0]
    assert "SELECT *" not in series_call["query"].upper()
    assert _table_fqdn(settings.bigquery_gold_dataset, "gold_fiscal_monetary") in series_call["query"]
    assert "`govdebt_GDP` AS value" in series_call["query"]
    assert series_call["params"]["country_codes"] == ["VNM", "THA"]
    assert series_call["params"]["start_year"] == 2010
    assert series_call["params"]["end_year"] == 2023


def test_compare_raw_returns_normalized_rows(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_agent_data_source", "bigquery")

    def fake_run(query: str, params: dict) -> list[dict]:
        if "GROUP BY country_code" in query:
            return [{"country_code": "THA", "country": "Thailand", "min_year": 2010, "max_year": 2023, "observations": 14}]
        return [
            {
                "country_code": "VNM",
                "country": "Vietnam",
                "year": 2010,
                "indicator": "govdebt_GDP",
                "value": 47.5,
                "unit": "%",
            }
        ]

    monkeypatch.setattr("app.tools.bigquery_tooling.run_bigquery_query", fake_run)

    result = compare_countries(
        indicator_code="govdebt_GDP",
        country_codes=["VNM", "THA"],
        start_year=2010,
        end_year=2023,
    )

    assert result["rows"]
    row = result["rows"][0]
    assert row["indicator"] == "govdebt_GDP"
    assert row["country"] == "Vietnam"
    assert row["year"] == 2010
    assert row["value"] == 47.5


def test_unsupported_indicator_does_not_call_bigquery(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_agent_data_source", "bigquery")
    called = {"count": 0}

    def fake_run(query: str, params: dict) -> list[dict]:
        called["count"] += 1
        return []

    monkeypatch.setattr("app.tools.bigquery_tooling.run_bigquery_query", fake_run)

    with pytest.raises(ToolError):
        compare_countries(
            indicator_code="flag_score",
            country_codes=["VNM", "THA"],
            start_year=2010,
            end_year=2023,
        )

    assert called["count"] == 0


def test_select_star_is_rejected() -> None:
    with pytest.raises(ToolError):
        execute_bigquery_select(
            sql=f"SELECT * FROM `{_table_fqdn(settings.bigquery_gold_dataset, 'gold_fiscal_monetary')}`",
            referenced_tables=[_table_fqdn(settings.bigquery_gold_dataset, "gold_fiscal_monetary")],
            params={},
        )


def test_non_whitelisted_table_is_rejected() -> None:
    with pytest.raises(ToolError):
        execute_bigquery_select(
            sql=f"SELECT country_code FROM `{settings.bigquery_project_id}.{settings.bigquery_gold_dataset}.some_other_table`",
            referenced_tables=[f"{settings.bigquery_project_id}.{settings.bigquery_gold_dataset}.some_other_table"],
            params={},
        )


def test_omitted_filters_do_not_send_null_params(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_agent_data_source", "bigquery")
    captured: dict[str, dict] = {}

    def fake_run(query: str, params: dict) -> list[dict]:
        captured["params"] = params
        return []

    monkeypatch.setattr("app.tools.bigquery_tooling.run_bigquery_query", fake_run)
    get_indicator_series(indicator_code="govdebt_GDP")

    assert captured["params"] == {"indicator_code": "govdebt_GDP", "unit": "%"}


def test_ranking_applies_limit_cap_and_ordering(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_agent_data_source", "bigquery")
    captured: dict[str, object] = {}

    def fake_run(query: str, params: dict) -> list[dict]:
        captured["query"] = query
        captured["params"] = params
        return []

    monkeypatch.setattr("app.tools.bigquery_tooling.run_bigquery_query", fake_run)

    rank_countries(
        indicator_code="govdebt_GDP",
        year=2023,
        limit=999,
        order="asc",
    )

    assert "ORDER BY value ASC" in str(captured["query"])
    assert captured["params"]["limit"] == 100
    assert "SELECT *" not in str(captured["query"]).upper()


def test_anomaly_unsupported_indicator_does_not_broaden(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_agent_data_source", "bigquery")
    called = {"count": 0}

    def fake_run(query: str, params: dict) -> list[dict]:
        called["count"] += 1
        return []

    monkeypatch.setattr("app.tools.bigquery_tooling.run_bigquery_query", fake_run)

    rows = get_indicator_anomalies(
        indicator_code="debt_change_YoY",
        country_codes=["VNM"],
        threshold=0.75,
        start_year=2010,
        end_year=2023,
        limit=10,
    )

    assert rows == []
    assert called["count"] == 0
