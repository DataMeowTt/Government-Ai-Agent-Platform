from fastapi import APIRouter, Depends

from app.core.security import verify_internal_api_key
from app.resolver.slot_resolver import resolve_slots, resolved_slots_to_metadata
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


@router.post("/chat", response_model=AiChatResponse)
def chat(payload: AiChatRequest) -> AiChatResponse:

    normalized_message = payload.message.strip()
    slots = resolve_slots(normalized_message)
    metadata = resolved_slots_to_metadata(slots)

    if slots.needs_clarification:
        answer = "Mình cần bạn làm rõ thêm: " + " ".join(slots.clarification_questions)
        question_type = "NEED_CLARIFICATION"
    else:
        indicator_codes = metadata["indicators"]
        country_codes = metadata["countries"]
        years = metadata["years"]

        answer = (
            "Phase 3 đã resolve metadata thành công. "
            f"Indicators={indicator_codes}, countries={country_codes}, years={years}. "
            "Phase sau sẽ dùng metadata này để lập query plan và gọi DB tool."
        )
        question_type = "VALID_SIMPLE_QUERY"

    return AiChatResponse(
        answer=answer,
        questionType=question_type,
        data=[
            {
                "message": normalized_message,
                "conversationId": payload.conversationId,
                "context": payload.context,
                "resolved": metadata["resolved"],
            }
        ],
        chart=AiAgentChartConfig(
            type="none",
            title=None,
            xKey=None,
            yKeys=None,
            data=None,
        ),
        warnings=[
            "Phase 3 mới resolve metadata, chưa query database và chưa gọi Gemini."
        ],
        metadata=AiAgentMetadata(
            source="mock",
            toolsUsed=["indicator_resolver", "country_resolver", "year_resolver"],
            indicators=metadata["indicators"],
            analytics_indicators=metadata["analytics_indicators"],
            raw_only_indicators=metadata["raw_only_indicators"],
            countries=metadata["countries"],
            years=metadata["years"],
            resolved=metadata["resolved"],
        ),
    )