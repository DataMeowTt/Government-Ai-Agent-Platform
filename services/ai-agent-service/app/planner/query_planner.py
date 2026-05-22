from app.planner.plan_schema import QueryPlan
from app.resolver.slot_resolver import ResolvedSlots
from app.catalog.analytics_catalog import indicator_has_analytics

def create_query_plan(question_type: str, slots: ResolvedSlots) -> QueryPlan:
    indicator_code = slots.indicators[0]["code"] if slots.indicators else None
    country_codes = [country["code"] for country in slots.countries]

    start_year = slots.start_year
    end_year = slots.end_year

    if question_type == "OFF_TOPIC":
        return QueryPlan(
            question_type=question_type,
            tool_name="none",
            arguments={},
        )

    if question_type in {"UNSUPPORTED", "UNSUPPORTED_DATA_QUERY"}:
        return QueryPlan(
            question_type=question_type,
            tool_name="none",
            arguments={},
            warnings=["Yêu cầu này hiện chưa được hỗ trợ."],
        )

    if question_type == "NEED_CLARIFICATION":
        return QueryPlan(
            question_type=question_type,
            tool_name="none",
            arguments={},
            warnings=slots.clarification_questions,
        )

    if not indicator_code:
        return QueryPlan(
            question_type="NEED_CLARIFICATION",
            tool_name="none",
            arguments={},
            warnings=[
                "Chưa xác định được indicator cần phân tích.",
            ],
        )

    if question_type == "VALID_COMPARE_QUERY":
        return QueryPlan(
            question_type=question_type,
            tool_name="compare_countries",
            arguments={
                "indicator_code": indicator_code,
                "country_codes": country_codes,
                "start_year": start_year,
                "end_year": end_year,
            },
        )

    if question_type == "VALID_RANKING_QUERY":
        year = end_year or start_year

        if year is None:
            return QueryPlan(
                question_type="NEED_CLARIFICATION",
                tool_name="none",
                arguments={},
                warnings=[
                    "Câu hỏi ranking cần có năm cụ thể, ví dụ: năm 2020.",
                ],
            )

        return QueryPlan(
            question_type=question_type,
            tool_name="rank_countries",
            arguments={
                "indicator_code": indicator_code,
                "year": year,
                "limit": 10,
                "order": "desc",
                "country_codes": country_codes,
            },
        )

    if question_type == "VALID_COVERAGE_QUERY":
        return QueryPlan(
            question_type=question_type,
            tool_name="get_data_coverage",
            arguments={
                "indicator_code": indicator_code,
                "country_codes": country_codes,
            },
        )

    if question_type == "VALID_TREND_QUERY":
        if indicator_has_analytics(indicator_code):
            return QueryPlan(
                question_type=question_type,
                tool_name="get_indicator_analytics_series",
                arguments={
                    "indicator_code": indicator_code,
                    "country_codes": country_codes,
                    "start_year": start_year,
                    "end_year": end_year,
                },
            )

        return QueryPlan(
            question_type=question_type,
            tool_name="get_indicator_series",
            arguments={
                "indicator_code": indicator_code,
                "country_codes": country_codes,
                "start_year": start_year,
                "end_year": end_year,
            },
            warnings=[
                "Indicator này chưa có analytics trend, dùng raw time series thay thế.",
            ],
        )

    if question_type == "VALID_ANOMALY_QUERY":
        if not indicator_has_analytics(indicator_code):
            return QueryPlan(
                question_type="UNSUPPORTED_DATA_QUERY",
                tool_name="none",
                arguments={},
                warnings=[
                    f"Indicator {indicator_code} chưa có analytics/anomaly score.",
                ],
            )

        return QueryPlan(
            question_type=question_type,
            tool_name="get_indicator_anomalies",
            arguments={
                "indicator_code": indicator_code,
                "country_codes": country_codes,
                "threshold": 0.75,
                "start_year": start_year,
                "end_year": end_year,
                "limit": 50,
            },
        )

    return QueryPlan(
        question_type="UNSUPPORTED_DATA_QUERY",
        tool_name="none",
        arguments={},
        warnings=[f"Planner chưa hỗ trợ question_type={question_type}."],
    )
