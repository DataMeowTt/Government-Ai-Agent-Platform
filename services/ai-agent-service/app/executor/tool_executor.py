from typing import Any

from app.planner.plan_schema import QueryPlan
from app.tools.analytics_series_tool import get_indicator_analytics_series
from app.tools.anomaly_tool import get_indicator_anomalies
from app.tools.compare_tool import compare_countries
from app.tools.coverage_tool import get_data_coverage
from app.tools.indicator_series_tool import get_indicator_series
from app.tools.ranking_tool import rank_countries


def execute_query_plan(plan: QueryPlan) -> dict[str, Any]:
    if plan.tool_name == "none":
        return {
            "tool": "none",
            "result": None,
        }

    if plan.tool_name == "compare_countries":
        return {
            "tool": plan.tool_name,
            "result": compare_countries(**plan.arguments),
        }

    if plan.tool_name == "rank_countries":
        return {
            "tool": plan.tool_name,
            "result": rank_countries(**plan.arguments),
        }

    if plan.tool_name == "get_data_coverage":
        return {
            "tool": plan.tool_name,
            "result": get_data_coverage(**plan.arguments),
        }

    if plan.tool_name == "get_indicator_series":
        return {
            "tool": plan.tool_name,
            "result": get_indicator_series(**plan.arguments),
        }
    if plan.tool_name == "get_indicator_analytics_series":
        return {
            "tool": plan.tool_name,
            "result": get_indicator_analytics_series(**plan.arguments),
        }

    if plan.tool_name == "get_indicator_anomalies":
        return {
            "tool": plan.tool_name,
            "result": get_indicator_anomalies(**plan.arguments),
        }
    raise ValueError(f"Unsupported tool_name: {plan.tool_name}")