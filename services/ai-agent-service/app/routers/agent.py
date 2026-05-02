from fastapi import APIRouter, Depends

from app.core.security import verify_internal_api_key
from app.executor.tool_executor import execute_query_plan
from app.planner.query_planner import create_query_plan
from app.resolver.slot_resolver import resolve_slots, resolved_slots_to_metadata
from app.router.rule_router import classify_question
from app.schemas.chat import (
    AiAgentChartConfig,
    AiAgentMetadata,
    AiChatRequest,
    AiChatResponse,
)


router = APIRouter(
    prefix="/agent",
    tags=["agent"],
    dependencies=[Depends(verify_internal_api_key)],
)


def build_compare_line_chart_data(rows: list[dict]) -> list[dict]:
    by_year: dict[int, dict] = {}

    for row in rows:
        year = row.get("year")
        country_code = row.get("country_code")
        value = row.get("value")

        if year is None or country_code is None:
            continue

        if year not in by_year:
            by_year[year] = {"year": year}

        by_year[year][country_code] = value

    return [by_year[year] for year in sorted(by_year.keys())]


def build_series_line_chart_data(rows: list[dict]) -> list[dict]:
    return [
        {
            "year": row.get("year"),
            "value": row.get("value"),
            "country_code": row.get("country_code"),
            "country": row.get("country"),
        }
        for row in rows
    ]


def make_metadata(
    metadata: dict,
    source: str,
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


@router.post("/chat", response_model=AiChatResponse)
def chat(payload: AiChatRequest) -> AiChatResponse:
    normalized_message = payload.message.strip()

    slots = resolve_slots(normalized_message)
    metadata = resolved_slots_to_metadata(slots)

    question_type = classify_question(normalized_message, slots)
    plan = create_query_plan(question_type, slots)

    base_tools = [
        "indicator_resolver",
        "country_resolver",
        "year_resolver",
        "rule_router",
        "query_planner",
    ]

    if question_type == "OFF_TOPIC":
        return AiChatResponse(
            answer=(
                "Câu hỏi này nằm ngoài phạm vi dữ liệu government/economic/social indicators. "
                "Bạn có thể hỏi về GDP, nợ công, lạm phát, thất nghiệp, nghèo đói, khủng hoảng, dân số, đô thị hóa..."
            ),
            questionType="OFF_TOPIC",
            data=[
                {
                    "message": normalized_message,
                    "resolved": metadata["resolved"],
                }
            ],
            chart=AiAgentChartConfig(type="none"),
            warnings=[],
            metadata=make_metadata(metadata, "template", base_tools),
        )

    if plan.question_type == "NEED_CLARIFICATION":
        clarification_questions = plan.warnings or slots.clarification_questions

        return AiChatResponse(
            answer="Mình cần bạn làm rõ thêm: " + " ".join(clarification_questions),
            questionType="NEED_CLARIFICATION",
            data=[
                {
                    "message": normalized_message,
                    "conversationId": payload.conversationId,
                    "context": payload.context,
                    "resolved": metadata["resolved"],
                }
            ],
            chart=AiAgentChartConfig(type="none"),
            warnings=clarification_questions,
            metadata=make_metadata(metadata, "template", base_tools),
        )

    if plan.question_type == "UNSUPPORTED_DATA_QUERY":
        return AiChatResponse(
            answer="Loại câu hỏi này chưa được hỗ trợ ở phase hiện tại.",
            questionType="UNSUPPORTED_DATA_QUERY",
            data=[
                {
                    "message": normalized_message,
                    "resolved": metadata["resolved"],
                    "plan": {
                        "question_type": plan.question_type,
                        "tool_name": plan.tool_name,
                        "arguments": plan.arguments,
                    },
                }
            ],
            chart=AiAgentChartConfig(type="none"),
            warnings=plan.warnings,
            metadata=make_metadata(metadata, "template", base_tools),
        )

    executed = execute_query_plan(plan)
    result = executed["result"]
    tool_name = executed["tool"]

    tools_used = [*base_tools, tool_name]

    indicator_code = metadata["indicators"][0] if metadata["indicators"] else None
    country_codes = metadata["countries"]
    start_year = metadata["resolved"].get("start_year")
    end_year = metadata["resolved"].get("end_year")

    if plan.question_type == "VALID_COMPARE_QUERY":
        rows = result["rows"]
        coverage = result["coverage"]
        chart_data = build_compare_line_chart_data(rows)

        answer = (
            f"Đã so sánh dữ liệu thật cho chỉ số {indicator_code} "
            f"của {', '.join(country_codes)}"
        )

        if start_year is not None and end_year is not None:
            answer += f" trong giai đoạn {start_year}-{end_year}"

        answer += f". Tìm thấy {len(rows)} dòng dữ liệu."

        return AiChatResponse(
            answer=answer,
            questionType="VALID_COMPARE_QUERY",
            data=[
                {
                    "message": normalized_message,
                    "conversationId": payload.conversationId,
                    "context": payload.context,
                    "resolved": metadata["resolved"],
                    "plan": {
                        "question_type": plan.question_type,
                        "tool_name": plan.tool_name,
                        "arguments": plan.arguments,
                    },
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
            metadata=make_metadata(metadata, "template", tools_used),
        )

    if plan.question_type == "VALID_RANKING_QUERY":
        rows = result
        year = plan.arguments.get("year")

        answer = (
            f"Đã xếp hạng top {len(rows)} quốc gia theo chỉ số {indicator_code} năm {year}."
        )

        return AiChatResponse(
            answer=answer,
            questionType="VALID_RANKING_QUERY",
            data=[
                {
                    "message": normalized_message,
                    "conversationId": payload.conversationId,
                    "context": payload.context,
                    "resolved": metadata["resolved"],
                    "plan": {
                        "question_type": plan.question_type,
                        "tool_name": plan.tool_name,
                        "arguments": plan.arguments,
                    },
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
                data=rows,
            ),
            warnings=[] if rows else ["Không tìm thấy dữ liệu ranking phù hợp."],
            metadata=make_metadata(metadata, "template", tools_used),
        )

    if plan.question_type == "VALID_COVERAGE_QUERY":
        rows = result

        answer = f"Đã kiểm tra coverage dữ liệu cho chỉ số {indicator_code}."

        return AiChatResponse(
            answer=answer,
            questionType="VALID_COVERAGE_QUERY",
            data=[
                {
                    "message": normalized_message,
                    "conversationId": payload.conversationId,
                    "context": payload.context,
                    "resolved": metadata["resolved"],
                    "plan": {
                        "question_type": plan.question_type,
                        "tool_name": plan.tool_name,
                        "arguments": plan.arguments,
                    },
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
            metadata=make_metadata(metadata, "template", tools_used),
        )

    if plan.question_type == "VALID_TREND_QUERY":
        rows = result
        chart_data = build_series_line_chart_data(rows)

        answer = f"Đã lấy chuỗi thời gian cho chỉ số {indicator_code}"

        if country_codes:
            answer += f" của {', '.join(country_codes)}"

        if start_year is not None and end_year is not None:
            answer += f" trong giai đoạn {start_year}-{end_year}"

        answer += f". Tìm thấy {len(rows)} dòng dữ liệu."

        return AiChatResponse(
            answer=answer,
            questionType="VALID_TREND_QUERY",
            data=[
                {
                    "message": normalized_message,
                    "conversationId": payload.conversationId,
                    "context": payload.context,
                    "resolved": metadata["resolved"],
                    "plan": {
                        "question_type": plan.question_type,
                        "tool_name": plan.tool_name,
                        "arguments": plan.arguments,
                    },
                    "indicator": indicator_code,
                    "countries": country_codes,
                    "rows": rows,
                }
            ],
            chart=AiAgentChartConfig(
                type="line" if rows else "none",
                title=f"{indicator_code} trend",
                xKey="year",
                yKeys=["value"],
                data=chart_data,
            ),
            warnings=[] if rows else ["Không tìm thấy dữ liệu chuỗi thời gian phù hợp."],
            metadata=make_metadata(metadata, "template", tools_used),
        )

    return AiChatResponse(
        answer="Planner đã tạo plan nhưng agent chưa biết compose response cho loại này.",
        questionType="UNSUPPORTED_DATA_QUERY",
        data=[
            {
                "message": normalized_message,
                "resolved": metadata["resolved"],
                "plan": {
                    "question_type": plan.question_type,
                    "tool_name": plan.tool_name,
                    "arguments": plan.arguments,
                },
            }
        ],
        chart=AiAgentChartConfig(type="none"),
        warnings=["Missing response composer for this plan type."],
        metadata=make_metadata(metadata, "template", tools_used),
    )