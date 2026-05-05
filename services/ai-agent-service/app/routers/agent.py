from typing import Literal

from fastapi import APIRouter, Depends

from app.composer.chart_composer import (
    build_anomaly_bar_chart_data,
    build_compare_line_chart_data,
    build_ranking_bar_chart_data,
    build_series_line_chart_data,
)
from app.composer.gemini_composer import compose_gemini_answer, should_use_gemini
from app.composer.template_composer import (
    compose_anomaly_answer,
    compose_compare_answer,
    compose_coverage_answer,
    compose_fallback_answer,
    compose_need_clarification_answer,
    compose_off_topic_answer,
    compose_ranking_answer,
    compose_trend_answer,
    compose_unsupported_answer,
)
from app.core.security import verify_internal_api_key
from app.executor.tool_executor import execute_query_plan
from app.parser.hybrid_parser import parse_with_hybrid_parser
from app.planner.plan_schema import QueryPlan
from app.resolver.slot_resolver import resolved_slots_to_metadata
from app.schemas.chat import (
    AiAgentChartConfig,
    AiAgentMetadata,
    AiChatRequest,
    AiChatResponse,
)


MetadataSource = Literal["template", "gemini", "mock"]


router = APIRouter(
    prefix="/agent",
    tags=["agent"],
    dependencies=[Depends(verify_internal_api_key)],
)


def make_metadata(
    metadata: dict,
    source: MetadataSource,
    tools_used: list[str],
) -> AiAgentMetadata:
    return AiAgentMetadata(
        source=source,
        toolsUsed=tools_used,
        indicators=metadata["indicators"],
        analytics_indicators=metadata["analytics_indicators"],
        raw_only_indicators=metadata["raw_only_indicators"],
        countries=metadata["countries"],
        years=metadata["years"],
        resolved=metadata["resolved"],
    )


def plan_to_dict(plan: QueryPlan) -> dict:
    return {
        "question_type": plan.question_type,
        "tool_name": plan.tool_name,
        "arguments": plan.arguments,
        "warnings": plan.warnings,
    }


def maybe_gemini_answer(
    user_message: str,
    question_type: str,
    indicator_code: str | None,
    result_payload: dict,
    template_answer: str,
    row_count: int,
) -> tuple[str, MetadataSource]:
    if not should_use_gemini(question_type, row_count):
        return template_answer, "template"

    answer = compose_gemini_answer(
        user_message=user_message,
        question_type=question_type,
        indicator_code=indicator_code,
        result_payload=result_payload,
        template_answer=template_answer,
    )

    if answer == template_answer:
        return answer, "template"

    return answer, "gemini"


@router.post("/chat", response_model=AiChatResponse)
def chat(payload: AiChatRequest) -> AiChatResponse:
    normalized_message = payload.message.strip()

    parse_result = parse_with_hybrid_parser(normalized_message, payload.context)
    slots = parse_result.slots
    metadata = resolved_slots_to_metadata(slots)

    question_type = parse_result.question_type
    plan = parse_result.plan

    if parse_result.parser_debug.get("source") == "model_parser":
        base_tools = [
            "parser_model_service",
            "model_parser_adapter",
            "query_planner",
        ]
    else:
        base_tools = [
            "indicator_resolver",
            "country_resolver",
            "year_resolver",
            "rule_router",
            "query_planner",
        ]

    response_debug = {
        "parsedQuery": parse_result.parsed_query,
        "parserDebug": parse_result.parser_debug,
    }

    indicator_code = metadata["indicators"][0] if metadata["indicators"] else None
    country_codes = metadata["countries"]
    start_year = metadata["resolved"].get("start_year")
    end_year = metadata["resolved"].get("end_year")

    if question_type == "OFF_TOPIC":
        return AiChatResponse(
            answer=compose_off_topic_answer(),
            questionType="OFF_TOPIC",
            status=parse_result.status or "off_topic",
            data=[
                {
                    "message": normalized_message,
                    "conversationId": payload.conversationId,
                    "context": payload.context,
                    "resolved": metadata["resolved"],
                    "plan": plan_to_dict(plan),
                }
            ],
            chart=AiAgentChartConfig(type="none"),
            warnings=[],
            metadata=make_metadata(metadata, "template", base_tools),
            **response_debug,
        )

    if plan.question_type == "NEED_CLARIFICATION":
        clarification_questions = plan.warnings or slots.clarification_questions

        return AiChatResponse(
            answer=compose_need_clarification_answer(clarification_questions),
            questionType="NEED_CLARIFICATION",
            status="needs_clarification",
            clarificationQuestions=clarification_questions,
            data=[
                {
                    "message": normalized_message,
                    "conversationId": payload.conversationId,
                    "context": payload.context,
                    "resolved": metadata["resolved"],
                    "plan": plan_to_dict(plan),
                }
            ],
            chart=AiAgentChartConfig(type="none"),
            warnings=clarification_questions,
            metadata=make_metadata(metadata, "template", base_tools),
            **response_debug,
        )

    
    if plan.question_type in {"UNSUPPORTED_DATA_QUERY", "UNSUPPORTED"}:
        return AiChatResponse(
            answer=compose_unsupported_answer(plan.warnings),
            questionType=plan.question_type,
            status="unsupported",
            data=[
                {
                    "message": normalized_message,
                    "conversationId": payload.conversationId,
                    "context": payload.context,
                    "resolved": metadata["resolved"],
                    "plan": plan_to_dict(plan),
                }
            ],
            chart=AiAgentChartConfig(type="none"),
            warnings=plan.warnings,
            metadata=make_metadata(metadata, "template", base_tools),
            **response_debug,
        )

    try:
        executed = execute_query_plan(plan)
    except Exception as error:
        return AiChatResponse(
            answer=compose_unsupported_answer(
                [
                    "Có lỗi khi chạy DB tool.",
                    str(error),
                ]
            ),
            questionType="UNSUPPORTED_DATA_QUERY",
            status="unsupported",
            data=[
                {
                    "message": normalized_message,
                    "conversationId": payload.conversationId,
                    "context": payload.context,
                    "resolved": metadata["resolved"],
                    "plan": plan_to_dict(plan),
                    "error": str(error),
                }
            ],
            chart=AiAgentChartConfig(type="none"),
            warnings=[
                "Tool execution failed.",
                str(error),
            ],
            metadata=make_metadata(metadata, "template", base_tools),
            **response_debug,
        )

    result = executed["result"]
    tool_name = executed["tool"]
    tools_used = [*base_tools, tool_name]

    
    if plan.question_type == "VALID_COMPARE_QUERY":
        rows = result["rows"]
        coverage = result["coverage"]
        chart_data = build_compare_line_chart_data(rows)

        template_answer = compose_compare_answer(
            indicator_code=indicator_code,
            country_codes=country_codes,
            start_year=start_year,
            end_year=end_year,
            rows=rows,
        )

        result_payload = {
            "indicator": indicator_code,
            "countries": country_codes,
            "coverage": coverage,
            "rows": rows,
        }

        answer, source = maybe_gemini_answer(
            user_message=normalized_message,
            question_type=plan.question_type,
            indicator_code=indicator_code,
            result_payload=result_payload,
            template_answer=template_answer,
            row_count=len(rows),
        )

        return AiChatResponse(
            answer=answer,
            questionType="VALID_COMPARE_QUERY",
            status="success",
            data=[
                {
                    "message": normalized_message,
                    "conversationId": payload.conversationId,
                    "context": payload.context,
                    "resolved": metadata["resolved"],
                    "plan": plan_to_dict(plan),
                    "indicator": indicator_code,
                    "countries": country_codes,
                    "coverage": coverage,
                    "rows": rows,
                }
            ],
            chart=AiAgentChartConfig(
                type="line" if rows else "none",
                title=f"{indicator_code} comparison",
                xKey="year",
                yKeys=country_codes,
                data=chart_data,
            ),
            warnings=[] if rows else ["Không tìm thấy dữ liệu phù hợp."],
            metadata=make_metadata(metadata, source, tools_used),
            **response_debug,
        )

    
    if plan.question_type == "VALID_RANKING_QUERY":
        rows = result
        year = plan.arguments.get("year")

        template_answer = compose_ranking_answer(
            indicator_code=indicator_code,
            year=year,
            rows=rows,
        )

        result_payload = {
            "indicator": indicator_code,
            "year": year,
            "rows": rows,
        }

        answer, source = maybe_gemini_answer(
            user_message=normalized_message,
            question_type=plan.question_type,
            indicator_code=indicator_code,
            result_payload=result_payload,
            template_answer=template_answer,
            row_count=len(rows),
        )

        return AiChatResponse(
            answer=answer,
            questionType="VALID_RANKING_QUERY",
            status="success",
            data=[
                {
                    "message": normalized_message,
                    "conversationId": payload.conversationId,
                    "context": payload.context,
                    "resolved": metadata["resolved"],
                    "plan": plan_to_dict(plan),
                    "indicator": indicator_code,
                    "year": year,
                    "rows": rows,
                }
            ],
            chart=AiAgentChartConfig(
                type="bar" if rows else "none",
                title=f"Top countries by {indicator_code} in {year}",
                xKey="country_code",
                yKeys=["value"],
                data=build_ranking_bar_chart_data(rows),
            ),
            warnings=[] if rows else ["Không tìm thấy dữ liệu ranking phù hợp."],
            metadata=make_metadata(metadata, source, tools_used),
            **response_debug,
        )

    
    if plan.question_type == "VALID_COVERAGE_QUERY":
        rows = result

        template_answer = compose_coverage_answer(
            indicator_code=indicator_code,
            rows=rows,
        )

        result_payload = {
            "indicator": indicator_code,
            "rows": rows,
        }

        answer, source = maybe_gemini_answer(
            user_message=normalized_message,
            question_type=plan.question_type,
            indicator_code=indicator_code,
            result_payload=result_payload,
            template_answer=template_answer,
            row_count=len(rows),
        )

        return AiChatResponse(
            answer=answer,
            questionType="VALID_COVERAGE_QUERY",
            status="success",
            data=[
                {
                    "message": normalized_message,
                    "conversationId": payload.conversationId,
                    "context": payload.context,
                    "resolved": metadata["resolved"],
                    "plan": plan_to_dict(plan),
                    "indicator": indicator_code,
                    "rows": rows,
                }
            ],
            chart=AiAgentChartConfig(
                type="table" if rows else "none",
                title=f"Coverage for {indicator_code}",
                xKey=None,
                yKeys=None,
                data=rows,
            ),
            warnings=[] if rows else ["Không tìm thấy coverage phù hợp."],
            metadata=make_metadata(metadata, source, tools_used),
            **response_debug,
        )

    
    if plan.question_type == "VALID_ANOMALY_QUERY":
        rows = result
        threshold = plan.arguments.get("threshold", 0.75)

        template_answer = compose_anomaly_answer(
            indicator_code=indicator_code,
            country_codes=country_codes,
            start_year=start_year,
            end_year=end_year,
            rows=rows,
            threshold=threshold,
        )

        result_payload = {
            "indicator": indicator_code,
            "countries": country_codes,
            "threshold": threshold,
            "rows": rows,
        }

        answer, source = maybe_gemini_answer(
            user_message=normalized_message,
            question_type=plan.question_type,
            indicator_code=indicator_code,
            result_payload=result_payload,
            template_answer=template_answer,
            row_count=len(rows),
        )

        return AiChatResponse(
            answer=answer,
            questionType="VALID_ANOMALY_QUERY",
            status="success",
            data=[
                {
                    "message": normalized_message,
                    "conversationId": payload.conversationId,
                    "context": payload.context,
                    "resolved": metadata["resolved"],
                    "plan": plan_to_dict(plan),
                    "indicator": indicator_code,
                    "countries": country_codes,
                    "threshold": threshold,
                    "rows": rows,
                }
            ],
            chart=AiAgentChartConfig(
                type="bar" if rows else "none",
                title=f"Anomalies for {indicator_code}",
                xKey="year",
                yKeys=["anomaly_score"],
                data=build_anomaly_bar_chart_data(rows),
            ),
            warnings=[] if rows else ["Không tìm thấy điểm bất thường phù hợp."],
            metadata=make_metadata(metadata, source, tools_used),
            **response_debug,
        )

    
    if plan.question_type == "VALID_TREND_QUERY":
        rows = result

        is_analytics_series = plan.tool_name == "get_indicator_analytics_series"

        if is_analytics_series:
            chart_data = rows
            y_keys = ["actual_value", "trend_value"]
            chart_title = f"{indicator_code} actual vs trend"
        else:
            chart_data = build_series_line_chart_data(rows)
            y_keys = ["value"]
            chart_title = f"{indicator_code} trend"

        template_answer = compose_trend_answer(
            indicator_code=indicator_code,
            country_codes=country_codes,
            start_year=start_year,
            end_year=end_year,
            rows=rows,
            is_analytics_series=is_analytics_series,
        )

        result_payload = {
            "indicator": indicator_code,
            "countries": country_codes,
            "is_analytics_series": is_analytics_series,
            "rows": rows,
        }

        answer, source = maybe_gemini_answer(
            user_message=normalized_message,
            question_type=plan.question_type,
            indicator_code=indicator_code,
            result_payload=result_payload,
            template_answer=template_answer,
            row_count=len(rows),
        )

        return AiChatResponse(
            answer=answer,
            questionType="VALID_TREND_QUERY",
            status="success",
            data=[
                {
                    "message": normalized_message,
                    "conversationId": payload.conversationId,
                    "context": payload.context,
                    "resolved": metadata["resolved"],
                    "plan": plan_to_dict(plan),
                    "indicator": indicator_code,
                    "countries": country_codes,
                    "is_analytics_series": is_analytics_series,
                    "rows": rows,
                }
            ],
            chart=AiAgentChartConfig(
                type="line" if rows else "none",
                title=chart_title,
                xKey="year",
                yKeys=y_keys,
                data=chart_data,
            ),
            warnings=[] if rows else ["Không tìm thấy dữ liệu chuỗi thời gian phù hợp."],
            metadata=make_metadata(metadata, source, tools_used),
            **response_debug,
        )

    
    return AiChatResponse(
        answer=compose_fallback_answer(
            {
                "question_type": plan.question_type,
                "tool_name": plan.tool_name,
            }
        ),
        questionType="UNSUPPORTED_DATA_QUERY",
        status="unsupported",
        data=[
            {
                "message": normalized_message,
                "conversationId": payload.conversationId,
                "context": payload.context,
                "resolved": metadata["resolved"],
                "plan": plan_to_dict(plan),
            }
        ],
        chart=AiAgentChartConfig(type="none"),
        warnings=["Missing response composer for this plan type."],
        metadata=make_metadata(metadata, "template", tools_used),
        **response_debug,
    )
