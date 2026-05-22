from typing import Any

from app.catalog.analytics_catalog import indicator_has_analytics
from app.planner.plan_schema import QueryPlan


def build_plan_from_validated_query(validated_query: dict[str, Any]) -> QueryPlan:
    intent = validated_query.get("intent")
    indicator_code = validated_query.get("indicator")
    countries = list(validated_query.get("countries") or [])
    start_year = validated_query.get("effective_start_year")
    end_year = validated_query.get("effective_end_year")
    warnings = list(validated_query.get("warnings") or [])

    if intent == "COMPARE_COUNTRIES":
        return QueryPlan(
            question_type="VALID_COMPARE_QUERY",
            tool_name="compare_countries",
            arguments={
                "indicator_code": indicator_code,
                "country_codes": countries,
                "start_year": start_year,
                "end_year": end_year,
            },
            warnings=warnings,
        )

    if intent == "RANKING":
        year = end_year or start_year or 2025
        return QueryPlan(
            question_type="VALID_RANKING_QUERY",
            tool_name="rank_countries",
            arguments={
                "indicator_code": indicator_code,
                "year": year,
                "limit": validated_query.get("limit") or 10,
                "order": validated_query.get("ranking_order") or "desc",
                "country_codes": countries,
            },
            warnings=warnings,
        )

    if intent == "COVERAGE":
        return QueryPlan(
            question_type="VALID_COVERAGE_QUERY",
            tool_name="get_data_coverage",
            arguments={
                "indicator_code": indicator_code,
                "country_codes": countries,
            },
            warnings=warnings,
        )

    if intent == "ANOMALY_DETECTION":
        return QueryPlan(
            question_type="VALID_ANOMALY_QUERY",
            tool_name="get_indicator_anomalies",
            arguments={
                "indicator_code": indicator_code,
                "country_codes": countries,
                "threshold": 0.75,
                "start_year": start_year,
                "end_year": end_year,
                "limit": validated_query.get("limit") or 50,
            },
            warnings=warnings,
        )

    if intent in {"TIME_SERIES", "TREND_ANALYSIS", "VALUE_LOOKUP"}:
        use_analytics = (
            indicator_has_analytics(indicator_code)
            and intent == "TREND_ANALYSIS"
            and indicator_code != "poverty_headcount"
        )
        tool_name = "get_indicator_analytics_series" if use_analytics else "get_indicator_series"
        return QueryPlan(
            question_type="VALID_TREND_QUERY",
            tool_name=tool_name,
            arguments={
                "indicator_code": indicator_code,
                "country_codes": countries,
                "start_year": start_year,
                "end_year": end_year,
            },
            warnings=warnings,
        )

    return QueryPlan(
        question_type="UNSUPPORTED_DATA_QUERY",
        tool_name="none",
        arguments={},
        warnings=["Dạng yêu cầu này hiện chưa được hỗ trợ trong dữ liệu hiện có."],
    )
