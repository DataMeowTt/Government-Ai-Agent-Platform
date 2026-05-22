from __future__ import annotations

from app.catalog.analytics_catalog import CLUSTER_TARGET_YEARS
from app.planner.validated_plan_adapter import build_plan_from_validated_query


def test_cluster_target_years_use_2025_not_2022() -> None:
    assert 2025 in CLUSTER_TARGET_YEARS
    assert 2022 not in CLUSTER_TARGET_YEARS


def test_ranking_default_year_is_2025() -> None:
    validated_query = {
        "intent": "RANKING",
        "indicator": "govdebt_GDP",
        "countries": [],
        "effective_start_year": None,
        "effective_end_year": None,
        "warnings": [],
    }

    plan = build_plan_from_validated_query(validated_query)
    assert plan.arguments["year"] == 2025


def test_ranking_allows_explicit_2022_when_provided() -> None:
    validated_query = {
        "intent": "RANKING",
        "indicator": "govdebt_GDP",
        "countries": [],
        "effective_start_year": 2022,
        "effective_end_year": 2022,
        "warnings": [],
    }

    plan = build_plan_from_validated_query(validated_query)
    assert plan.arguments["year"] == 2022
