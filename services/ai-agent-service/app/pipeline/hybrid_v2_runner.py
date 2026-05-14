import logging
from dataclasses import asdict, is_dataclass
from typing import Any

from app.composer.chart_composer import (
    build_anomaly_bar_chart_data,
    build_compare_line_chart_data,
    build_ranking_bar_chart_data,
    build_series_line_chart_data,
)
from app.composer.deterministic_guard import append_result_warnings
from app.composer.display_formatter import (
    format_value,
    get_country_label,
    get_direction_text,
    get_indicator_label,
    get_indicator_unit,
    safe_number,
    sanitize_user_facing_text,
)
from app.composer.template_composer import (
    compose_anomaly_answer,
    compose_compare_answer,
    compose_coverage_answer,
    compose_need_clarification_answer,
    compose_no_data_answer,
    compose_off_topic_answer,
    compose_ranking_answer,
    compose_trend_answer,
    compose_unsupported_answer,
    sanitize_clarification_questions,
)
from app.conversation.context_store import (
    make_assistant_turn,
    make_user_turn,
    summarize_rows,
    update_conversation_context,
)
from app.conversation.followup_merge import merge_followup_query
from app.core.config import settings
from app.executor.tool_executor import execute_query_plan
from app.catalog.canonical_indicator_catalog import normalize_catalog_text, resolve_indicator_alias
from app.catalog.country_group_catalog import resolve_country_groups
from app.parser.normalization_guard import normalize_parser_output
from app.parser.parser_service_client import call_parser_service
from app.planner.validated_plan_adapter import build_plan_from_validated_query
from app.resolver.country_resolver import resolve_countries
from app.router.front_router_adapter import build_front_router_draft_from_existing_router
from app.router.front_llm_router import route_with_front_llm_draft
from app.router.rule_first_router import run_rule_first_router
from app.schemas.chat import AiAgentChartConfig, AiAgentMetadata, AiChatRequest, AiChatResponse
from app.validator.query_validator import validate_parsed_candidate
from app.validator.result_validator import result_validation_to_dict, validate_tool_result


logger = logging.getLogger(__name__)


def run_hybrid_v2_pipeline(
    payload: AiChatRequest,
    message: str,
    previous_context: dict[str, Any],
    router_context: dict[str, Any],
    router_decision: Any | None = None,
) -> AiChatResponse | None:
    try:
        rule_draft = run_rule_first_router(message, router_context)
        front_draft = build_front_router_draft_from_existing_router(None, rule_draft)
        front_router_decision = None
        executed_front_router = False
        model_parsed: dict[str, Any] | None = None
        parser_model_debug: dict[str, Any] = {
            "executed_model_parser": False,
            "parserServiceAvailable": False,
            "parserModelDebug": {},
        }

        if rule_draft.route == "GENERAL_EXPLANATION" and not rule_draft.needs_front_llm:
            return _direct_explanation_response(
                payload=payload,
                message=message,
                rule_draft=rule_draft,
                router_debug=_router_debug(
                    "GENERAL_EXPLANATION",
                    rule_draft,
                    front_draft,
                    front_router_decision,
                    executed_front_router,
                    parser_model_debug,
                ),
            )

        if _should_execute_front_router(rule_draft):
            front_router_decision = router_decision or _route_with_front_llm(message, router_context, rule_draft)
            executed_front_router = front_router_decision is not None
            router_result = _decision_to_dict(front_router_decision)
            front_draft = build_front_router_draft_from_existing_router(router_result, rule_draft)

        if front_draft.route == "GENERAL_EXPLANATION":
            return _direct_explanation_response(
                payload=payload,
                message=message,
                rule_draft=rule_draft,
                router_debug=_router_debug(
                    "GENERAL_EXPLANATION",
                    rule_draft,
                    front_draft,
                    front_router_decision,
                    executed_front_router,
                    parser_model_debug,
                ),
                answer_override=front_draft.answer,
            )

        if front_draft.route == "FOLLOW_UP_ANALYSIS":
            return _followup_analysis_response(
                payload,
                message,
                previous_context,
                router_context,
                rule_draft,
                _router_debug(
                    "FOLLOW_UP_ANALYSIS",
                    rule_draft,
                    front_draft,
                    front_router_decision,
                    executed_front_router,
                    parser_model_debug,
                ),
            )

        if front_draft.route == "NEED_CLARIFICATION":
            questions = [front_draft.clarification_question] if front_draft.clarification_question else front_draft.clarification_questions
            return _clarification_response(
                payload,
                message,
                questions,
                rule_draft,
                router_debug=_router_debug(
                    "NEED_CLARIFICATION",
                    rule_draft,
                    front_draft,
                    front_router_decision,
                    executed_front_router,
                    parser_model_debug,
                ),
            )

        if front_draft.route == "OFF_TOPIC":
            return _off_topic_response(
                payload,
                message,
                rule_draft,
                _router_debug(
                    "OFF_TOPIC",
                    rule_draft,
                    front_draft,
                    front_router_decision,
                    executed_front_router,
                    parser_model_debug,
                ),
            )

        if front_draft.route == "UNSUPPORTED":
            return _front_unsupported_response(
                payload=payload,
                message=message,
                rule_draft=rule_draft,
                front_draft=front_draft,
                router_debug=_router_debug(
                    "UNSUPPORTED",
                    rule_draft,
                    front_draft,
                    front_router_decision,
                    executed_front_router,
                    parser_model_debug,
                ),
            )

        standalone_query = _standalone_query_from_front_or_rule(
            message=message,
            previous_context=previous_context,
            rule_draft=rule_draft,
            front_draft=front_draft,
        )

        if _should_call_parser_model(message, rule_draft, front_draft):
            model_parsed, parser_model_debug = _call_parser_model_candidate(
                standalone_query=standalone_query,
                original_message=message,
                rule_draft=rule_draft,
                front_draft=front_draft,
            )

        candidate = normalize_parser_output(
            parsed=model_parsed,
            standalone_query=standalone_query,
            route=front_draft.route or rule_draft.route or "DATA_QUERY",
            front_draft=front_draft,
            rule_draft=rule_draft,
        )
        validation = validate_parsed_candidate(candidate)

        router_debug = _router_debug(
            validation.validated_query.get("route") if validation.validated_query else _debug_route_for_invalid(candidate, validation),
            rule_draft,
            front_draft,
            front_router_decision,
            executed_front_router,
            parser_model_debug,
        )

        if not validation.ok:
            if validation.status == "needs_clarification":
                return _clarification_response(payload, message, validation.clarification_questions, rule_draft, candidate, validation, router_debug)
            if validation.status == "unsupported":
                return _unsupported_response(payload, message, validation.unsupported_terms, rule_draft, candidate, validation, router_debug)
            if validation.status == "no_data":
                return _no_data_response(payload, message, validation, router_debug)
            return None

        if not validation.validated_query:
            return None

        if validation.validated_query.get("intent") in {"DIRECT_ANSWER", "GENERAL_EXPLANATION"}:
            return _direct_explanation_response(
                payload=payload,
                message=message,
                rule_draft=rule_draft,
                router_debug=_router_debug(
                    validation.validated_query.get("route") or validation.validated_query.get("intent"),
                    rule_draft,
                    front_draft,
                    front_router_decision,
                    executed_front_router,
                    parser_model_debug,
                ),
                answer_override=front_draft.answer,
            )

        if validation.validated_query.get("intent") == "OFF_TOPIC":
            return _off_topic_response(
                payload=payload,
                message=message,
                rule_draft=rule_draft,
                router_debug=_router_debug(
                    "OFF_TOPIC",
                    rule_draft,
                    front_draft,
                    front_router_decision,
                    executed_front_router,
                    parser_model_debug,
                ),
            )

        plan = build_plan_from_validated_query(validation.validated_query)
        if plan.tool_name == "none":
            return _unsupported_response(
                payload=payload,
                message=message,
                unsupported_terms=["Dạng yêu cầu này hiện chưa được hỗ trợ"],
                rule_draft=rule_draft,
                candidate=candidate,
                validation=validation,
                router_debug=_router_debug(
                    validation.validated_query.get("route") or "DATA_QUERY",
                    rule_draft,
                    front_draft,
                    front_router_decision,
                    executed_front_router,
                    parser_model_debug,
                ),
            )

        executed = execute_query_plan(plan)
        result = executed["result"]
        rows = _rows_from_result(result, plan.question_type)
        result_validation = validate_tool_result(rows, validation.validated_query)
        return _data_response(
            payload=payload,
            message=message,
            candidate=candidate,
            validation=validation,
            plan=plan,
            tool_name=executed["tool"],
            result=result,
            rows=rows,
            result_validation=result_validation_to_dict(result_validation),
            rule_draft=rule_draft,
            router_debug=router_debug,
        )
    except Exception as error:
        logger.exception(
            "Hybrid v2 pipeline failed, fallback_to_legacy=%s: %s",
            settings.enable_hybrid_v2_fallback,
            error,
        )
        if settings.enable_hybrid_v2_fallback:
            return None
        raise


def _followup_analysis_response(
    payload: AiChatRequest,
    message: str,
    previous_context: dict[str, Any],
    router_context: dict[str, Any],
    rule_draft: Any,
    router_debug: dict[str, Any] | None = None,
) -> AiChatResponse:
    summary = router_context.get("last_data_summary") or {}
    answer = _compose_followup_analysis_from_context(router_context, message)

    response = AiChatResponse(
        answer=sanitize_user_facing_text(answer),
        questionType="VALID_SIMPLE_QUERY",
        status="success",
        data=[
            {
                "message": message,
                "route": "FOLLOW_UP_ANALYSIS",
                "previousDataSummary": summary,
            }
        ],
        chart=AiAgentChartConfig(type="none"),
        warnings=[],
        metadata=_metadata(
            "template",
            ["rule_first_router", "conversation_context"],
            rule_draft=rule_draft,
        ),
        parsedQuery=previous_context.get("last_parsed_query") or None,
        parserDebug=None,
        routerDebug=router_debug
        or {
            "route": "FOLLOW_UP_ANALYSIS",
            "pipeline": "hybrid_v2",
            "ruleFirst": asdict(rule_draft),
            "executed_front_router": False,
            "executed_model_parser": False,
            "executed_parser_agent": False,
            "executed_db": False,
            "needs_parser": False,
            "needs_db": False,
        },
    )

    update_conversation_context(
        payload.conversationId,
        {
            "last_user_message": message,
            "last_answer": response.answer,
            "last_route": "FOLLOW_UP_ANALYSIS",
            "last_status": "success",
            "last_question_type": response.questionType,
            "append_recent_turns": [
                make_user_turn(message),
                make_assistant_turn(response.answer, "success", response.questionType, "FOLLOW_UP_ANALYSIS"),
            ],
        },
    )

    return response

def _compose_followup_analysis_from_context(router_context: dict[str, Any], message: str = "") -> str:
    summary = router_context.get("last_data_summary") or {}
    rows = summary.get("top_rows") or router_context.get("last_rows") or []
    question_type = router_context.get("last_question_type")
    indicator_code = summary.get("indicator")
    indicator_label = get_indicator_label(indicator_code) if indicator_code else "kết quả trước đó"
    unit = get_indicator_unit(indicator_code)

    row_count = summary.get("row_count")
    period = _context_period_text(summary)
    normalized_message = normalize_catalog_text(message)
    asks_reason = any(
        token in normalized_message
        for token in (
            "vi sao",
            "tai sao",
            "ly do",
            "nguyen nhan",
            "phan tich",
            "giai thich",
        )
    )
    asks_commonality = any(
        token in normalized_message
        for token in (
            "diem chung",
            "cac nuoc nay",
            "nhom nay",
            "giong nhau",
            "dac diem chung",
        )
    )
    asks_risk = any(
        token in normalized_message
        for token in (
            "rui ro",
            "rủi ro",
            "canh bao",
            "dang lo",
            "bat on",
        )
    )
    qualitative_text = _qualitative_followup_text(indicator_code, message)

    if not rows:
        detail = f" với {row_count} dòng dữ liệu" if row_count else ""
        return sanitize_user_facing_text(
            f"Dựa trên {indicator_label}{detail}, có thể đưa ra nhận xét định tính. "
            f"{qualitative_text} "
            "Đây là phân tích định tính, không phải bằng chứng nhân quả trực tiếp."
        )

    if question_type == "VALID_RANKING_QUERY":
        first_row = _first_numeric_row(rows)
        if first_row:
            country = get_country_label(first_row)
            value = format_value(_context_row_value(first_row), unit)
            order = summary.get("order")
            order_text = "cao nhất" if order == "desc" else "thấp nhất" if order == "asc" else "nổi bật"
            return sanitize_user_facing_text(
                f"Kết quả trước là xếp hạng {indicator_label}{period}. "
                f"Nhóm đứng {order_text} bắt đầu với {country} ở mức {value}. "
                f"{qualitative_text} "
                "Đây là phân tích định tính, không phải bằng chứng nhân quả trực tiếp."
            )

    grouped = _context_rows_by_country(rows)
    final_rows: list[dict] = []

    for country_code, country_rows in grouped.items():
        numeric_rows = [row for row in country_rows if safe_number(_context_row_value(row)) is not None]
        if not numeric_rows:
            continue
        numeric_rows.sort(key=lambda row: int(row.get("year") or 0))
        first = numeric_rows[0]
        last = numeric_rows[-1]
        final_rows.append(last)
        country = get_country_label(last, country_code=country_code)
        direction = get_direction_text(_context_row_value(first), _context_row_value(last))

        if len(grouped) == 1:
            return sanitize_user_facing_text(
                f"Kết quả trước cho thấy {indicator_label} của {country}{period} "
                f"đi từ {format_value(_context_row_value(first), unit)} năm {first.get('year')} "
                f"đến {format_value(_context_row_value(last), unit)} năm {last.get('year')}, xu hướng chung là {direction}. "
                f"{qualitative_text} "
                "Đây là phân tích định tính, không phải bằng chứng nhân quả trực tiếp."
            )

    if len(final_rows) >= 2:
        highest = max(final_rows, key=lambda row: safe_number(_context_row_value(row)))
        lowest = min(final_rows, key=lambda row: safe_number(_context_row_value(row)))

        high_country = get_country_label(highest)
        low_country = get_country_label(lowest)
        high_value = format_value(_context_row_value(highest), unit)
        low_value = format_value(_context_row_value(lowest), unit)
        year = highest.get("year") or lowest.get("year")

        return sanitize_user_facing_text(
            f"Kết quả trước cho thấy ở cuối kỳ {year}, {high_country} có {indicator_label} cao hơn "
            f"({high_value}), còn {low_country} thấp hơn ({low_value}) trong nhóm dữ liệu đã hiển thị. "
            f"{qualitative_text} "
            "Chênh lệch này nên được hiểu như mô tả dữ liệu, không tự động chứng minh nguyên nhân. "
            "Đây là phân tích định tính, không phải bằng chứng nhân quả trực tiếp."
        )

    return sanitize_user_facing_text(
        f"Dựa trên kết quả đã hiển thị cho {indicator_label}{period}, có thể rút ra nhận xét định tính. "
        f"{qualitative_text} "
        "Đây là phân tích định tính, không phải bằng chứng nhân quả trực tiếp."
    )


def _qualitative_followup_text(indicator_code: str | None, message: str) -> str:
    normalized = normalize_catalog_text(message)
    label = get_indicator_label(indicator_code) if indicator_code else "chỉ số đang xét"

    asks_commonality = any(
        token in normalized
        for token in (
            "diem chung",
            "cac nuoc nay",
            "nhom nay",
            "giong nhau",
            "dac diem chung",
        )
    )
    asks_risk = any(
        token in normalized
        for token in (
            "rui ro",
            "canh bao",
            "dang lo",
            "bat on",
        )
    )

    if asks_commonality:
        return (
            f"Điểm chung cần chú ý là các nước trong kết quả đều nổi bật về {label} trong phạm vi dữ liệu đã hiển thị. "
            "Điều này thường phản ánh một số đặc điểm tương đồng về bối cảnh vĩ mô, cấu trúc kinh tế, chu kỳ tăng trưởng, "
            "chính sách công hoặc chất lượng dữ liệu, nhưng không nên hiểu là các nước có cùng nguyên nhân."
        )

    if asks_risk:
        if indicator_code in {"govdebt_GDP", "debt_change_YoY", "cumulative_deficit_5yr"}:
            return (
                "Rủi ro định tính chính là dư địa tài khóa có thể thu hẹp, chi phí vay tăng, áp lực trả nợ lớn hơn "
                "và khả năng ứng phó với cú sốc kinh tế kém linh hoạt hơn."
            )
        if indicator_code in {"inflation_cpi", "inflation_deflator", "inflation_gap", "rolling_3yr_avg_cpi"}:
            return (
                "Rủi ro định tính chính là sức mua suy giảm, chi phí sinh hoạt tăng, lãi suất có thể chịu áp lực tăng "
                "và kỳ vọng lạm phát trở nên khó kiểm soát hơn."
            )
        if indicator_code in {"unemployment_total", "unemployment_youth", "youth_unemployment_gap"}:
            return (
                "Rủi ro định tính chính là thu nhập hộ gia đình suy yếu, áp lực an sinh tăng, kỹ năng lao động bị lãng phí "
                "và tăng trưởng dài hạn có thể bị ảnh hưởng."
            )
        if indicator_code in {"poverty_headcount", "poverty_change_5yr"}:
            return (
                "Rủi ro định tính chính là mức sống dễ bị tổn thương hơn trước cú sốc giá cả, việc làm hoặc suy giảm tăng trưởng, "
                "đồng thời nhu cầu hỗ trợ an sinh có thể tăng."
            )
        return (
            f"Rủi ro định tính liên quan đến {label} thường nằm ở ổn định vĩ mô, dư địa chính sách, khả năng chống chịu "
            "trước cú sốc và sự khác biệt về chất lượng dữ liệu giữa các nước."
        )

    if indicator_code in {"govdebt_GDP", "debt_change_YoY", "cumulative_deficit_5yr"}:
        return (
            "Về mặt định tính, nợ công/GDP có thể tăng khi thâm hụt ngân sách kéo dài, tăng trưởng GDP chậm, "
            "chi phí vay cao hoặc chính phủ phải mở rộng chi tiêu trong giai đoạn khủng hoảng. "
            "Nó có thể giảm khi tăng trưởng GDP nhanh hơn tốc độ tăng nợ hoặc ngân sách cải thiện."
        )

    if indicator_code in {"inflation_cpi", "inflation_deflator", "inflation_gap", "rolling_3yr_avg_cpi"}:
        return (
            "Về mặt định tính, lạm phát có thể tăng do cú sốc giá hàng hóa, mất giá tiền tệ, chính sách tiền tệ nới lỏng, "
            "đứt gãy cung ứng hoặc cầu nội địa tăng nhanh. Khi các yếu tố này hạ nhiệt, lạm phát thường giảm dần."
        )

    if indicator_code in {"unemployment_total", "unemployment_youth", "youth_unemployment_gap"}:
        return (
            "Về mặt định tính, thất nghiệp chịu ảnh hưởng bởi chu kỳ kinh tế, tốc độ tạo việc làm, cơ cấu ngành, "
            "chất lượng kỹ năng lao động và các cú sốc như suy thoái hoặc dịch bệnh."
        )

    if indicator_code in {"poverty_headcount", "poverty_change_5yr"}:
        return (
            "Về mặt định tính, tỷ lệ nghèo thường giảm khi thu nhập và việc làm cải thiện, tăng trưởng lan tỏa tốt hơn, "
            "giá cả ổn định và chính sách an sinh hiệu quả. Ngược lại, cú sốc giá, thất nghiệp hoặc suy giảm tăng trưởng "
            "có thể làm nghèo dai dẳng hơn."
        )

    if indicator_code in {"tax_revenue_pct_GDP", "fiscal_balance_GDP", "govrev_GDP", "govexp_GDP"}:
        return (
            "Về mặt định tính, khác biệt tài khóa có thể đến từ năng lực thu ngân sách, cấu trúc thuế, quy mô chi tiêu công, "
            "chu kỳ kinh tế và mức độ tuân thủ thuế."
        )

    if indicator_code in {"trade_pct_gdp", "GFCF_to_GDP", "GNI_to_GDP"}:
        return (
            f"Về mặt định tính, khác biệt về {label} thường phản ánh độ mở nền kinh tế, cấu trúc sản xuất, dòng vốn, "
            "thương mại quốc tế và chính sách phát triển của từng nước."
        )

    return (
        f"Về mặt định tính, khác biệt về {label} thường phản ánh bối cảnh kinh tế, cấu trúc chính sách, "
        "chu kỳ tăng trưởng, năng lực quản trị và chất lượng dữ liệu khác nhau giữa các nước."
    )


def _context_period_text(summary: dict[str, Any]) -> str:
    start_year = summary.get("start_year")
    end_year = summary.get("end_year")
    year = summary.get("year")

    if year:
        return f" năm {year}"
    if start_year and end_year:
        if start_year == end_year:
            return f" năm {start_year}"
        return f" giai đoạn {start_year}-{end_year}"
    if start_year:
        return f" từ năm {start_year}"
    if end_year:
        return f" đến năm {end_year}"
    return ""


def _context_row_value(row: dict[str, Any]) -> Any:
    if row.get("value") is not None:
        return row.get("value")
    if row.get("actual_value") is not None:
        return row.get("actual_value")
    return None


def _first_numeric_row(rows: list[dict]) -> dict | None:
    for row in rows:
        if safe_number(_context_row_value(row)) is not None:
            return row
    return None


def _context_rows_by_country(rows: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        code = row.get("country_code")
        if not code:
            continue
        grouped.setdefault(str(code), []).append(row)
    return grouped

def _direct_explanation_response(
    payload: AiChatRequest,
    message: str,
    rule_draft: Any,
    router_debug: dict[str, Any] | None = None,
    answer_override: str | None = None,
) -> AiChatResponse:
    answer = _safe_direct_answer(answer_override) or _compose_direct_explanation_template(message)
    response = AiChatResponse(
        answer=sanitize_user_facing_text(answer),
        questionType="VALID_SIMPLE_QUERY",
        status="success",
        data=[
            {
                "message": message,
                "route": "GENERAL_EXPLANATION",
            }
        ],
        chart=AiAgentChartConfig(type="none"),
        warnings=[],
        metadata=_metadata("template", ["rule_first_router", "direct_explanation_template"], rule_draft=rule_draft),
        parsedQuery=None,
        parserDebug=None,
        routerDebug=router_debug or {"route": "GENERAL_EXPLANATION", "pipeline": "hybrid_v2"},
    )
    _update_basic(
        payload.conversationId,
        message,
        response.answer,
        "GENERAL_EXPLANATION",
        "success",
        response.questionType,
        extra_patch={
            "last_general_explanation": {
                "topic": message,
                "summary": response.answer,
            },
        },
    )
    return response


def _safe_direct_answer(answer: str | None) -> str | None:
    text = sanitize_user_facing_text(str(answer or "").strip())
    if len(text) < 20:
        return None
    lowered = text.lower()
    forbidden = ("router", "parser", "database", " db", "sql", "tool", "gemini", "ngrok")
    if any(token in lowered for token in forbidden):
        return None
    return text


def _compose_direct_explanation_template(message: str) -> str:
    normalized = normalize_catalog_text(message)
    raw_lower = message.lower()

    if "gdp per capita" in normalized or "bình quân đầu người" in normalized or "binh quan dau nguoi" in normalized or "income per capita" in normalized:
        return (
            "GDP per capita là GDP bình quân đầu người: GDP tổng chia cho dân số. "
            "Trong dữ liệu hiện có, chỉ số gần nhất là GDP thực bình quân đầu người ở dạng log, "
            "nên giá trị dùng để so sánh là thang log chứ không phải USD trực tiếp."
        )

    if "trade openness" in normalized or "độ mở thương mại" in normalized or "do mo thuong mai" in normalized:
        return (
            "Trade openness là tỷ lệ tổng thương mại so với GDP. "
            "Chỉ số này thường cho biết mức độ nền kinh tế gắn với trao đổi hàng hóa và dịch vụ với bên ngoài."
        )

    if (
        "tang truong gdp thuc" in normalized
        or "real gdp growth" in normalized
        or "rgdp growth" in normalized
        or "gdp thuc yoy" in normalized
    ):
        return (
            "Tăng trưởng GDP thực YoY là tốc độ tăng của GDP thực so với năm trước, "
            "đã loại bớt ảnh hưởng của thay đổi giá. Chỉ số này thường dùng để đánh giá "
            "nền kinh tế tăng trưởng thực chất nhanh hay chậm qua từng năm."
        )

    if "poverty headcount" in normalized or "ty le ngheo" in normalized or "tỷ lệ nghèo" in raw_lower:
        return (
            "Poverty headcount là tỷ lệ dân số sống dưới ngưỡng nghèo. "
            "Chỉ số này thường dùng để đánh giá mức độ nghèo đói và khả năng bao phủ "
            "của tăng trưởng, việc làm và chính sách an sinh đối với người dân."
        )

    if "reer deviation" in normalized or "do lech reer" in normalized or "độ lệch reer" in raw_lower:
        return (
            "REER deviation là độ lệch của tỷ giá hiệu dụng thực so với xu hướng hoặc mức tham chiếu. "
            "Chỉ số này giúp nhận diện áp lực mất cân đối tỷ giá, khả năng đồng tiền bị định giá cao/thấp "
            "và rủi ro cạnh tranh bên ngoài."
        )
    if "fiscal balance" in normalized or "budget balance" in normalized or "cán cân ngân sách" in normalized or "can can ngan sach" in normalized:
        return (
            "Fiscal balance/GDP là cán cân ngân sách so với GDP. "
            "Giá trị dương thường là thặng dư ngân sách, còn giá trị âm thường là thâm hụt ngân sách."
        )

    if "gfcf" in normalized or "gross fixed capital formation" in normalized or "đầu tư cố định" in normalized or "dau tu co dinh" in normalized:
        return (
            "GFCF to GDP là đầu tư tài sản cố định so với GDP, phản ánh phần sản lượng được dành cho "
            "máy móc, nhà xưởng, hạ tầng và các tài sản cố định khác."
        )

    if "real interest rate" in normalized or "lãi suất thực" in normalized or "lai suat thuc" in normalized:
        return "Real interest rate là lãi suất thực sau khi điều chỉnh lạm phát, giúp nhìn chi phí vay theo sức mua thực tế."

    if "coverage" in normalized:
        return "Coverage dữ liệu cho biết một chỉ số có dữ liệu ở những quốc gia nào, từ năm nào đến năm nào và có bao nhiêu quan sát."

    if "nợ công" in normalized or "no cong" in normalized or "public debt" in normalized or "government debt" in normalized:
        return "Nợ công/GDP là tỷ lệ nợ công so với GDP, dùng để đánh giá quy mô nợ khu vực công so với quy mô nền kinh tế."

    if "lạm phát cpi" in normalized or "lam phat cpi" in normalized or "cpi" in normalized:
        return "Lạm phát CPI là mức tăng của chỉ số giá tiêu dùng, phản ánh thay đổi giá của rổ hàng hóa và dịch vụ tiêu dùng."

    if "that nghiep" in normalized or "unemployment" in normalized or "thất nghiệp" in raw_lower:
        return (
            "Tỷ lệ thất nghiệp phản ánh phần lực lượng lao động đang không có việc làm "
            "nhưng có nhu cầu và sẵn sàng làm việc. Chỉ số này thường được dùng để đánh giá "
            "sức khỏe thị trường lao động và mức độ hấp thụ việc làm của nền kinh tế."
        )

    if "tax revenue" in normalized or "thu thuế" in normalized or "thu thue" in normalized:
        return "Tax revenue/GDP là thu thuế so với GDP, thường dùng để đánh giá năng lực huy động nguồn thu thuế của một nền kinh tế."

    return (
        "Đây là câu hỏi giải thích khái niệm trong phạm vi dữ liệu kinh tế - xã hội. "
        "Bạn có thể nêu rõ chỉ số như nợ công/GDP, lạm phát CPI, thất nghiệp, tăng trưởng GDP hoặc độ mở thương mại để mình giải thích cụ thể hơn."
    )


def _clarification_response(
    payload: AiChatRequest,
    message: str,
    questions: list[str],
    rule_draft: Any,
    candidate: Any | None = None,
    validation: Any | None = None,
    router_debug: dict[str, Any] | None = None,
) -> AiChatResponse:
    clean_questions = sanitize_clarification_questions(questions)
    answer = compose_need_clarification_answer(clean_questions)
    response = AiChatResponse(
        answer=answer,
        questionType="NEED_CLARIFICATION",
        status="needs_clarification",
        clarificationQuestions=clean_questions,
        data=[{"message": message, "route": "NEED_CLARIFICATION"}],
        chart=AiAgentChartConfig(type="none"),
        warnings=clean_questions,
        metadata=_metadata("template", ["rule_first_router"], rule_draft=rule_draft, candidate=candidate, validation=validation),
        parsedQuery=asdict(candidate) if candidate else None,
        parserDebug=_parser_debug_from_candidate(candidate, router_debug),
        routerDebug=router_debug or {"route": "NEED_CLARIFICATION", "pipeline": "hybrid_v2", "ruleFirst": asdict(rule_draft)},
    )
    _update_basic(payload.conversationId, message, answer, "NEED_CLARIFICATION", "needs_clarification", response.questionType)
    return response


def _unsupported_response(
    payload: AiChatRequest,
    message: str,
    unsupported_terms: list[str],
    rule_draft: Any,
    candidate: Any,
    validation: Any,
    router_debug: dict[str, Any] | None = None,
) -> AiChatResponse:
    warnings = (
        ["Chỉ số này chưa có trong dữ liệu hiện tại hoặc chưa được hỗ trợ."]
        if unsupported_terms
        else [validation.reason]
    )
    answer = compose_unsupported_answer(warnings)
    response = AiChatResponse(
        answer=answer,
        questionType="UNSUPPORTED_DATA_QUERY",
        status="unsupported",
        data=[{"message": message, "route": "UNSUPPORTED", "unsupportedTerms": unsupported_terms}],
        chart=AiAgentChartConfig(type="none"),
        warnings=[],
        metadata=_metadata("template", ["rule_first_router", "normalization_guard", "query_validator"], rule_draft=rule_draft, candidate=candidate, validation=validation, unsupported_terms=unsupported_terms),
        parsedQuery=asdict(candidate),
        parserDebug=_parser_debug_from_candidate(candidate, router_debug),
        routerDebug=router_debug or {"route": "DATA_QUERY", "intent": "UNSUPPORTED", "pipeline": "hybrid_v2", "ruleFirst": asdict(rule_draft)},
    )
    _update_basic(payload.conversationId, message, answer, "UNSUPPORTED", "unsupported", response.questionType, parsed_query=asdict(candidate))
    return response


def _front_unsupported_response(
    payload: AiChatRequest,
    message: str,
    rule_draft: Any,
    front_draft: Any,
    router_debug: dict[str, Any] | None = None,
) -> AiChatResponse:
    warning = front_draft.reason or "Yêu cầu này hiện chưa được hỗ trợ trong dữ liệu hiện có."
    answer = compose_unsupported_answer([warning])
    response = AiChatResponse(
        answer=answer,
        questionType="UNSUPPORTED_DATA_QUERY",
        status="unsupported",
        data=[{"message": message, "route": "UNSUPPORTED"}],
        chart=AiAgentChartConfig(type="none"),
        warnings=[],
        metadata=_metadata("template", ["rule_first_router", "front_llm_router"], rule_draft=rule_draft),
        parsedQuery=None,
        parserDebug=None,
        routerDebug=router_debug or {"route": "UNSUPPORTED", "pipeline": "hybrid_v2", "ruleFirst": asdict(rule_draft)},
    )
    _update_basic(payload.conversationId, message, answer, "UNSUPPORTED", "unsupported", response.questionType)
    return response


def _off_topic_response(
    payload: AiChatRequest,
    message: str,
    rule_draft: Any,
    router_debug: dict[str, Any] | None = None,
) -> AiChatResponse:
    answer = compose_off_topic_answer()
    response = AiChatResponse(
        answer=answer,
        questionType="OFF_TOPIC",
        status="off_topic",
        data=[{"message": message, "route": "OFF_TOPIC"}],
        chart=AiAgentChartConfig(type="none"),
        warnings=[],
        metadata=_metadata("template", ["rule_first_router"], rule_draft=rule_draft),
        parsedQuery=None,
        parserDebug=None,
        routerDebug=router_debug or {"route": "OFF_TOPIC", "pipeline": "hybrid_v2", "ruleFirst": asdict(rule_draft)},
    )
    _update_basic(payload.conversationId, message, answer, "OFF_TOPIC", "off_topic", response.questionType)
    return response


def _legacy_no_data_response_unused(
    payload: AiChatRequest,
    message: str,
    validation: Any,
    router_debug: dict[str, Any] | None = None,
) -> AiChatResponse:
    answer = "Không tìm thấy dữ liệu phù hợp cho yêu cầu này."
    response = AiChatResponse(
        answer=answer,
        questionType="NO_DATA",
        status="no_data",
        data=[{"message": message, "route": "DATA_QUERY"}],
        chart=AiAgentChartConfig(type="none"),
        warnings=validation.warnings,
        metadata=_metadata("template", ["query_validator"], validation=validation),
        parsedQuery=None,
        parserDebug=None,
        routerDebug=router_debug or {"route": "DATA_QUERY", "pipeline": "hybrid_v2", "status": "no_data"},
    )
    _update_basic(payload.conversationId, message, answer, "DATA_QUERY", "no_data", response.questionType)
    return response


def _no_data_response(
    payload: AiChatRequest,
    message: str,
    validation: Any,
    router_debug: dict[str, Any] | None = None,
) -> AiChatResponse:
    answer = compose_no_data_answer(
        validation_reason=getattr(validation, "reason", None),
        warnings=getattr(validation, "warnings", []),
        validated_query=getattr(validation, "validated_query", None),
    )
    response = AiChatResponse(
        answer=answer,
        questionType="NO_DATA",
        status="no_data",
        data=[
            {
                "message": message,
                "route": "DATA_QUERY",
                "validation": asdict(validation) if validation else None,
            }
        ],
        chart=AiAgentChartConfig(type="none"),
        warnings=getattr(validation, "warnings", []),
        metadata=_metadata("template", ["query_validator"], validation=validation),
        parsedQuery=getattr(validation, "validated_query", None),
        parserDebug=None,
        routerDebug=router_debug or {"route": "DATA_QUERY", "pipeline": "hybrid_v2", "status": "no_data"},
    )
    _update_basic(payload.conversationId, message, answer, "DATA_QUERY", "no_data", response.questionType)
    return response

def _empty_result_no_data_response(
    payload: AiChatRequest,
    message: str,
    candidate: Any,
    validation: Any,
    plan: Any,
    rows: list[dict],
    result_validation: dict[str, Any],
    rule_draft: Any,
    router_debug: dict[str, Any],
    warnings: list[str],
) -> AiChatResponse:
    validated_query = validation.validated_query or {}

    answer = compose_no_data_answer(
        validation_reason="Không tìm thấy dữ liệu phù hợp trong kết quả truy vấn.",
        warnings=warnings,
        validated_query=validated_query,
    )

    data_item = {
        "message": message,
        "conversationId": payload.conversationId,
        "resolved": _resolved_metadata(validated_query),
        "plan": _plan_to_dict(plan),
        "route": validated_query.get("route"),
        "indicator": validated_query.get("indicator"),
        "countries": validated_query.get("countries") or [],
        "rows": rows,
        "resultValidation": result_validation,
    }

    response = AiChatResponse(
        answer=sanitize_user_facing_text(answer),
        questionType="NO_DATA",
        status="no_data",
        data=[data_item],
        chart=AiAgentChartConfig(type="none"),
        warnings=warnings,
        metadata=_metadata(
            "template",
            ["rule_first_router", "parser_model_service", "normalization_guard", "query_validator", "validated_plan_adapter", plan.tool_name, "result_validator"],
            rule_draft=rule_draft,
            candidate=candidate,
            validation=validation,
            result_validation=result_validation,
            unsupported_terms=validation.unsupported_terms,
            missing_countries=result_validation.get("missing_countries", []),
            validated_query=validated_query,
        ),
        parsedQuery=asdict(candidate),
        parserDebug=_parser_debug_from_candidate(candidate, router_debug),
        routerDebug={
            **router_debug,
            "route": validated_query.get("route"),
            "executed_parser_agent": False,
            "executed_db": True,
            "status": "no_data",
            "needs_parser": True,
            "needs_db": bool(rule_draft.needs_db),
        },
    )

    update_conversation_context(
        payload.conversationId,
        {
            "last_user_message": message,
            "last_answer": response.answer,
            "last_route": validated_query.get("route") or "DATA_QUERY",
            "last_status": "no_data",
            "last_question_type": response.questionType,
            "last_parsed_query": asdict(candidate),
            "last_validated_query": validated_query,
            "last_query_plan": _plan_to_dict(plan),
            "last_rows": [],
            "last_chart": {},
            "last_result_validation": result_validation,
            "append_recent_turns": [
                make_user_turn(message),
                make_assistant_turn(response.answer, "no_data", response.questionType, validated_query.get("route") or "DATA_QUERY"),
            ],
            "last_data_summary": {
                "indicator": validated_query.get("indicator"),
                "countries": validated_query.get("countries") or [],
                "years": [
                    year
                    for year in (
                        validated_query.get("effective_start_year"),
                        validated_query.get("effective_end_year"),
                    )
                    if year
                ],
                "start_year": validated_query.get("effective_start_year"),
                "end_year": validated_query.get("effective_end_year"),
                "row_count": 0,
                "top_rows": [],
            },
        },
    )

    return response

def _data_response(
    payload: AiChatRequest,
    message: str,
    candidate: Any,
    validation: Any,
    plan: Any,
    tool_name: str,
    result: Any,
    rows: list[dict],
    result_validation: dict[str, Any],
    rule_draft: Any,
    router_debug: dict[str, Any],
) -> AiChatResponse:
    validated_query = validation.validated_query or {}
    indicator_code = validated_query.get("indicator")
    countries = validated_query.get("countries") or []
    start_year = validated_query.get("effective_start_year")
    end_year = validated_query.get("effective_end_year")
    warnings = _dedupe_strings([*validation.warnings, *plan.warnings, *result_validation.get("warnings", [])])
    question_type = plan.question_type

    if result_validation.get("is_empty") and not (
        question_type == "VALID_ANOMALY_QUERY"
        and result_validation.get("empty_result_kind") == "no_anomaly_detected"
    ):
        return _empty_result_no_data_response(
            payload=payload,
            message=message,
            candidate=candidate,
            validation=validation,
            plan=plan,
            rows=rows,
            result_validation=result_validation,
            rule_draft=rule_draft,
            router_debug=router_debug,
            warnings=warnings,
        )

    if question_type == "VALID_COMPARE_QUERY":
        result_rows = result.get("rows", rows) if isinstance(result, dict) else rows
        answer = compose_compare_answer(indicator_code, countries, start_year, end_year, result_rows, result_validation)
        chart = AiAgentChartConfig(type="line" if result_rows else "none", title=f"So sánh {get_indicator_label(indicator_code)}", xKey="year", yKeys=countries, data=build_compare_line_chart_data(result_rows))
        data_item = {"indicator": indicator_code, "countries": countries, "coverage": result.get("coverage", []) if isinstance(result, dict) else [], "rows": result_rows}
    elif question_type == "VALID_RANKING_QUERY":
        answer = compose_ranking_answer(indicator_code, plan.arguments.get("year"), rows, plan.arguments.get("limit"), plan.arguments.get("order"))
        chart = AiAgentChartConfig(type="bar" if rows else "none", title=f"Top quốc gia theo {get_indicator_label(indicator_code)}", xKey="country_code", yKeys=["value"], data=build_ranking_bar_chart_data(rows))
        data_item = {"indicator": indicator_code, "year": plan.arguments.get("year"), "rows": rows}
    elif question_type == "VALID_COVERAGE_QUERY":
        answer = compose_coverage_answer(indicator_code, rows)
        chart = AiAgentChartConfig(type="table" if rows else "none", title=f"Phạm vi dữ liệu {get_indicator_label(indicator_code)}", data=rows)
        data_item = {"indicator": indicator_code, "rows": rows}
    elif question_type == "VALID_ANOMALY_QUERY":
        threshold = plan.arguments.get("threshold", 0.75)
        answer = compose_anomaly_answer(indicator_code, countries, start_year, end_year, rows, threshold=threshold)
        chart = AiAgentChartConfig(type="bar" if rows else "none", title=f"Điểm bất thường của {get_indicator_label(indicator_code)}", xKey="year", yKeys=["anomaly_score"], data=build_anomaly_bar_chart_data(rows))
        data_item = {"indicator": indicator_code, "countries": countries, "threshold": threshold, "rows": rows}
    else:
        is_analytics = plan.tool_name == "get_indicator_analytics_series"
        answer = compose_trend_answer(indicator_code, countries, start_year, end_year, rows, is_analytics)
        chart_data = rows if is_analytics else build_series_line_chart_data(rows)
        y_keys = ["actual_value", "trend_value"] if is_analytics else ["value"]
        chart = AiAgentChartConfig(type="line" if rows else "none", title=f"Xu hướng {get_indicator_label(indicator_code)}", xKey="year", yKeys=y_keys, data=chart_data)
        data_item = {"indicator": indicator_code, "countries": countries, "is_analytics_series": is_analytics, "rows": rows}

    answer = append_result_warnings(sanitize_user_facing_text(answer), warnings)
    metadata = _metadata(
        "template",
        ["rule_first_router", "parser_model_service", "normalization_guard", "query_validator", "validated_plan_adapter", tool_name, "result_validator"],
        rule_draft=rule_draft,
        candidate=candidate,
        validation=validation,
        result_validation=result_validation,
        unsupported_terms=validation.unsupported_terms,
        missing_countries=result_validation.get("missing_countries", []),
        validated_query=validated_query,
    )
    data_item = {
        "message": message,
        "conversationId": payload.conversationId,
        "resolved": _resolved_metadata(validated_query),
        "plan": _plan_to_dict(plan),
        "route": validated_query.get("route"),
        "resultValidation": result_validation,
        **data_item,
    }
    response = AiChatResponse(
        answer=answer,
        questionType=question_type,
        status="success",
        data=[data_item],
        chart=chart,
        warnings=warnings,
        metadata=metadata,
        parsedQuery=asdict(candidate),
        parserDebug=_parser_debug_from_candidate(candidate, router_debug),
        routerDebug={
            **router_debug,
            "route": validated_query.get("route"),
            "executed_parser_agent": False,
            "executed_db": True,
            "needs_parser": True,
            "needs_db": bool(rule_draft.needs_db),
        },
    )
    _update_query_success(payload.conversationId, message, response, candidate, validated_query, plan, rows, chart, result_validation)
    return response


def _rows_from_result(result: Any, question_type: str) -> list[dict]:
    if question_type == "VALID_COMPARE_QUERY" and isinstance(result, dict):
        return result.get("rows") or []
    if isinstance(result, list):
        return result
    return []


def _debug_route_for_invalid(candidate: Any, validation: Any) -> str:
    if validation.status in {"unsupported", "no_data"}:
        return "DATA_QUERY"
    if validation.status == "needs_clarification":
        return "NEED_CLARIFICATION"
    route = getattr(candidate, "route", None)
    return route if route else str(validation.status)


def _looks_like_general_explanation(message: str) -> bool:
    normalized = normalize_catalog_text(message)
    raw_lower = message.lower()

    direct_patterns = (
        "la gi",
        "nghia la gi",
        "y nghia",
        "cach hieu",
        "dung de",
        "phan anh dieu gi",
        "phan anh gi",
        "cho biet dieu gi",
        "dung de danh gia",
        "noi len dieu gi",
        "the hien dieu gi",
        "khac gi",
    )

    raw_patterns = (
        "là gì",
        "nghĩa là gì",
        "ý nghĩa",
        "cách hiểu",
        "dùng để",
        "phản ánh điều gì",
        "phản ánh gì",
        "cho biết điều gì",
        "dùng để đánh giá",
        "nói lên điều gì",
        "thể hiện điều gì",
        "khác gì",
    )

    return any(pattern in normalized for pattern in direct_patterns) or any(
        pattern in raw_lower for pattern in raw_patterns
    )


def _should_execute_front_router(rule_draft: Any) -> bool:
    return bool(rule_draft.needs_front_llm or rule_draft.confidence < 0.9)


def _route_with_front_llm(message: str, router_context: dict[str, Any], rule_draft: Any | None = None) -> Any:
    return route_with_front_llm_draft(
        user_message=message,
        conversation_context=router_context,
        rule_route_draft=rule_draft,
    )


def _decision_to_dict(decision: Any | None) -> dict[str, Any] | None:
    if decision is None:
        return None
    if isinstance(decision, dict):
        return decision
    if hasattr(decision, "to_dict"):
        return decision.to_dict()
    if is_dataclass(decision):
        return asdict(decision)
    return None


def _should_call_parser_model(message: str, rule_draft: Any, front_draft: Any) -> bool:
    front_route = getattr(front_draft, "route", None)
    rule_route = getattr(rule_draft, "route", None)
    route = front_route or rule_route

    if front_route in {"OFF_TOPIC", "FOLLOW_UP_ANALYSIS", "NEED_CLARIFICATION", "UNSUPPORTED", "GENERAL_EXPLANATION"}:
        return False
    if not (bool(getattr(front_draft, "needs_parser", False)) or bool(getattr(rule_draft, "needs_parser_agent", False))):
        return False
    if rule_draft.confidence >= 0.9 and rule_draft.draft_indicators and not _has_complex_slots(message):
        return False
    if _has_enough_deterministic_slots(message, rule_draft, front_draft):
        confidence = max(
            float(rule_draft.confidence or 0.0),
            float(front_draft.confidence or rule_draft.confidence or 0.0),
        )
        if confidence >= 0.85:
            return False

    combined_indicators = _dedupe_strings([*rule_draft.draft_indicators, *front_draft.draft_indicators])
    combined_countries = _dedupe_strings([*rule_draft.draft_countries, *front_draft.draft_countries])
    combined_groups = _dedupe_strings([*rule_draft.draft_country_groups, *front_draft.draft_country_groups])
    intent = front_draft.intent_hint or rule_draft.intent_hint

    if not rule_draft.matched:
        return True
    if rule_draft.confidence < 0.85:
        return True
    if front_draft.confidence < 0.85:
        return True
    if (route in {"DATA_QUERY", "FOLLOW_UP_MODIFY_QUERY"} or intent) and not combined_indicators:
        return True
    if intent == "COMPARE_COUNTRIES" and len(combined_countries) + len(combined_groups) < 2:
        return True
    if intent in {"TREND_ANALYSIS", "TIME_SERIES", "VALUE_LOOKUP"} and not combined_countries and not combined_groups:
        return True
    if intent == "COVERAGE" and not combined_indicators:
        return True
    return _has_complex_slots(message) and min(rule_draft.confidence, front_draft.confidence) < 0.9


def _standalone_query_from_front_or_rule(
    *,
    message: str,
    previous_context: dict[str, Any],
    rule_draft: Any,
    front_draft: Any,
) -> str:
    if front_draft and front_draft.rewritten_query:
        return front_draft.rewritten_query

    if rule_draft.route == "FOLLOW_UP_MODIFY_QUERY" and rule_draft.delta:
        previous_query = (
            previous_context.get("last_data_query")
            or previous_context.get("last_validated_query")
            or previous_context.get("last_parsed_query")
            or {}
        )
        merged_query = merge_followup_query(previous_query, rule_draft.delta)
        return _query_dict_to_standalone_text(merged_query) or message

    return message


def _query_dict_to_standalone_text(query: dict[str, Any]) -> str:
    if not isinstance(query, dict) or not query:
        return ""

    intent = query.get("intent") or _infer_intent_from_query(query)
    indicator = query.get("indicator") or (query.get("indicators") or [None])[0]
    countries = list(query.get("countries") or [])
    groups = list(query.get("country_groups") or [])
    start_year = query.get("start_year") or query.get("effective_start_year")
    end_year = query.get("end_year") or query.get("effective_end_year")
    limit = query.get("limit")
    order = query.get("ranking_order") or query.get("order")

    subjects = [*countries, *groups]
    subject_text = ", ".join(subjects)
    period_text = ""
    if start_year and end_year:
        period_text = f" từ {start_year} đến {end_year}"
    elif end_year or start_year:
        period_text = f" năm {end_year or start_year}"

    if intent == "COMPARE_COUNTRIES":
        return f"So sánh {indicator} của {subject_text}{period_text}".strip()
    if intent == "RANKING":
        order_text = "thấp nhất" if order == "asc" else "cao nhất"
        limit_text = f"Top {limit or 10} nước"
        return f"{limit_text} có {indicator} {order_text}{period_text}".strip()
    if intent == "COVERAGE":
        return f"Coverage dữ liệu {indicator} của {subject_text}".strip()
    if intent == "ANOMALY_DETECTION":
        target = f" của {subject_text}" if subject_text else ""
        return f"Phát hiện bất thường {indicator}{target}{period_text}".strip()
    target = f" của {subject_text}" if subject_text else ""
    return f"Xu hướng {indicator}{target}{period_text}".strip()


def _has_enough_deterministic_slots(message: str, rule_draft: Any, front_draft: Any) -> bool:
    resolver_indicator = resolve_indicator_alias(message)
    resolver_countries = [match.country.code for match in resolve_countries(message)]
    resolver_groups = [match.group.code for match in resolve_country_groups(message)]

    indicators = _dedupe_strings(
        [
            *rule_draft.draft_indicators,
            *front_draft.draft_indicators,
            *([resolver_indicator.indicator.code] if resolver_indicator else []),
        ]
    )
    countries = _dedupe_strings(
        [
            *rule_draft.draft_countries,
            *front_draft.draft_countries,
            *resolver_countries,
        ]
    )
    groups = _dedupe_strings(
        [
            *rule_draft.draft_country_groups,
            *front_draft.draft_country_groups,
            *resolver_groups,
        ]
    )
    intent = front_draft.intent_hint or rule_draft.intent_hint

    if not indicators:
        return False
    if intent == "COMPARE_COUNTRIES":
        return len(countries) + len(groups) >= 2
    if intent == "RANKING":
        return True
    if intent == "COVERAGE":
        return True
    if intent in {"TREND_ANALYSIS", "TIME_SERIES", "VALUE_LOOKUP"}:
        return len(countries) + len(groups) >= 1
    if indicators and (countries or groups):
        return True
    return False


def _has_complex_slots(message: str) -> bool:
    normalized = message.lower()
    years = [token for token in normalized.split() if token.isdigit() and len(token) == 4]
    slot_markers = sum(
        1
        for token in (" so sánh ", " compare ", " vs ", ",", " và ", " and ", " top ", " thấp nhất", " cao nhất")
        if token in f" {normalized} "
    )
    return len(years) >= 2 and slot_markers >= 2


def _call_parser_model_candidate(
    *,
    standalone_query: str,
    original_message: str,
    rule_draft: Any,
    front_draft: Any,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    parser_response = call_parser_service(
        standalone_query,
        context={
            "original_user_message": original_message,
            "standalone_query": standalone_query,
            "rule_route": getattr(rule_draft, "route", None),
            "rule_intent_hint": getattr(rule_draft, "intent_hint", None),
            "front_route": getattr(front_draft, "route", None),
            "front_uses_previous_context": getattr(front_draft, "uses_previous_context", False),
        },
    )

    parsed = parser_response.get("parsed") if isinstance(parser_response, dict) else None
    parser_debug = _parser_model_debug(parser_response)

    debug = {
        "executed_model_parser": True,
        "parserServiceAvailable": isinstance(parser_response, dict),
        "parserModelDebug": parser_debug,
    }

    if _parser_response_is_safe(parser_response) and isinstance(parsed, dict):
        return parsed, debug

    return None, debug


def _parser_response_is_safe(parser_response: Any) -> bool:
    if not isinstance(parser_response, dict):
        return False

    parsed = parser_response.get("parsed")
    if not isinstance(parsed, dict):
        return False

    schema_pass = bool(
        parser_response.get("deployment_schema_pass")
        or parser_response.get("schema_pass")
    )

    allowed_intents = {
        item.strip()
        for item in settings.parser_hybrid_allowed_intents.split(",")
        if item.strip()
    }

    return (
        parser_response.get("safe_to_execute") is True
        and parser_response.get("catalog_pass") is True
        and schema_pass
        and parsed.get("intent") in allowed_intents
    )


def _parser_model_debug(parser_response: Any) -> dict[str, Any]:
    if not isinstance(parser_response, dict):
        return {
            "safe_to_execute": False,
            "catalog_pass": False,
            "schema_pass": False,
            "deployment_schema_pass": False,
            "fallback_reason": "parser_service_unavailable",
            "latency_ms": None,
            "intent": None,
        }

    parsed = parser_response.get("parsed") if isinstance(parser_response.get("parsed"), dict) else {}
    return {
        "safe_to_execute": parser_response.get("safe_to_execute"),
        "catalog_pass": parser_response.get("catalog_pass"),
        "schema_pass": parser_response.get("schema_pass"),
        "deployment_schema_pass": parser_response.get("deployment_schema_pass"),
        "fallback_reason": parser_response.get("fallback_reason"),
        "latency_ms": parser_response.get("latency_ms"),
        "intent": parsed.get("intent"),
    }


def _router_debug(
    route: str | None,
    rule_draft: Any,
    front_draft: Any,
    front_router_decision: Any | None,
    executed_front_router: bool,
    parser_model_debug: dict[str, Any],
) -> dict[str, Any]:
    front_decision_dict = _decision_to_dict(front_router_decision)
    return {
        "route": route,
        "pipeline": "hybrid_v2",
        "executed_front_router": executed_front_router,
        "frontRouter": asdict(front_draft) if front_draft else None,
        "frontRouterDecision": front_decision_dict,
        "ruleFirst": asdict(rule_draft),
        "executed_model_parser": bool(parser_model_debug.get("executed_model_parser")),
        "parserServiceAvailable": bool(parser_model_debug.get("parserServiceAvailable")),
        "parserModelDebug": parser_model_debug.get("parserModelDebug") or {},
        "executed_parser_agent": False,
        "executed_db": False,
        "needs_parser": bool(getattr(front_draft, "needs_parser", False) or rule_draft.needs_parser_agent),
        "needs_db": bool(getattr(front_draft, "needs_db", False) or rule_draft.needs_db),
    }


def _model_parsed_from_query(query: dict[str, Any]) -> dict[str, Any]:
    indicators = query.get("indicators") or ([query["indicator"]] if query.get("indicator") else [])
    return {
        "intent": query.get("intent") or _infer_intent_from_query(query),
        "indicators": indicators,
        "countries": query.get("countries") or [],
        "country_groups": query.get("country_groups") or [],
        "start_year": query.get("start_year") or query.get("effective_start_year"),
        "end_year": query.get("end_year") or query.get("effective_end_year"),
        "limit": query.get("limit"),
        "ranking_order": query.get("ranking_order"),
    }


def _infer_intent_from_query(query: dict[str, Any]) -> str:
    countries = list(query.get("countries") or [])
    country_groups = list(query.get("country_groups") or [])

    if query.get("limit") or query.get("ranking_order"):
        return "RANKING"

    if len(countries) >= 2:
        return "COMPARE_COUNTRIES"

    if country_groups and (query.get("limit") or query.get("ranking_order")):
        return "RANKING"

    if countries or country_groups:
        return "TIME_SERIES"

    return "VALUE_LOOKUP"


def _dedupe_strings(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return result


def _parser_debug_from_candidate(candidate: Any | None, router_debug: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if candidate is None:
        return None

    debug = {
        "source": getattr(candidate, "source", "normalization_guard"),
        "confidence": getattr(candidate, "confidence", None),
        "reason": getattr(candidate, "reason", ""),
        "candidate_sources": getattr(candidate, "candidate_sources", {}),
    }

    model_debug = (router_debug or {}).get("parserModelDebug") or {}
    if model_debug:
        debug["modelParserDebug"] = model_debug

    return debug


def _metadata(
    source: str,
    tools_used: list[str],
    rule_draft: Any | None = None,
    candidate: Any | None = None,
    validation: Any | None = None,
    result_validation: dict[str, Any] | None = None,
    unsupported_terms: list[str] | None = None,
    missing_countries: list[str] | None = None,
    validated_query: dict[str, Any] | None = None,
) -> AiAgentMetadata:
    query = validated_query or (validation.validated_query if validation and validation.validated_query else {})
    indicators = query.get("indicators") or (candidate.indicators if candidate else [])
    countries = query.get("countries") or (candidate.countries if candidate else [])
    years = [year for year in (query.get("effective_start_year"), query.get("effective_end_year")) if isinstance(year, int)]
    return AiAgentMetadata(
        source=source,
        toolsUsed=tools_used,
        indicators=list(indicators),
        analytics_indicators=[],
        raw_only_indicators=list(indicators),
        countries=list(countries),
        years=sorted(set(years)),
        resolved=_resolved_metadata(query) if query else None,
        validation=asdict(validation) if validation else None,
        resultValidation=result_validation,
        ruleFirst=asdict(rule_draft) if rule_draft else None,
        parserAgent=asdict(candidate) if candidate else None,
        unsupportedTerms=unsupported_terms or [],
        missingCountries=missing_countries or [],
        pipeline="hybrid_v2",
        fallbackUsed=False,
    )


def _resolved_metadata(query: dict[str, Any]) -> dict[str, Any]:
    return {
        "indicators": query.get("indicators") or [],
        "countries": query.get("countries") or [],
        "country_groups": query.get("country_groups") or [],
        "start_year": query.get("effective_start_year"),
        "end_year": query.get("effective_end_year"),
        "limit": query.get("limit"),
        "ranking_order": query.get("ranking_order"),
        "needs_clarification": False,
        "clarification_questions": [],
    }


def _plan_to_dict(plan: Any) -> dict[str, Any]:
    return {
        "question_type": plan.question_type,
        "tool_name": plan.tool_name,
        "arguments": plan.arguments,
        "warnings": plan.warnings,
    }


def _update_basic(
    conversation_id: str | None,
    message: str,
    answer: str,
    route: str,
    status: str,
    question_type: str,
    parsed_query: dict[str, Any] | None = None,
    extra_patch: dict[str, Any] | None = None,
) -> None:
    patch = {
        "last_user_message": message,
        "last_answer": answer,
        "last_route": route,
        "last_status": status,
        "last_question_type": question_type,
        "append_recent_turns": [
            make_user_turn(message),
            make_assistant_turn(answer, status, question_type, route),
        ],
    }
    if parsed_query is not None:
        patch["last_parsed_query"] = parsed_query
    if extra_patch:
        patch.update(extra_patch)
    update_conversation_context(conversation_id, patch)


def _update_query_success(
    conversation_id: str | None,
    message: str,
    response: AiChatResponse,
    candidate: Any,
    validated_query: dict[str, Any],
    plan: Any,
    rows: list[dict],
    chart: AiAgentChartConfig,
    result_validation: dict[str, Any],
) -> None:
    row_summary = summarize_rows(rows, settings.conversation_context_max_rows)
    chart_dict = chart.model_dump()
    chart_without_data = {key: value for key, value in chart_dict.items() if key != "data"}
    last_data_query = {
        "intent": validated_query.get("intent"),
        "indicator": validated_query.get("indicator"),
        "indicators": validated_query.get("indicators") or [],
        "countries": validated_query.get("countries") or [],
        "country_groups": validated_query.get("country_groups") or [],
        "start_year": validated_query.get("effective_start_year"),
        "end_year": validated_query.get("effective_end_year"),
        "limit": validated_query.get("limit"),
        "ranking_order": validated_query.get("ranking_order"),
    }
    last_result_summary = {
        "row_count": result_validation.get("row_count", row_summary["row_count"]),
        "actual_start_year": result_validation.get("actual_start_year") or result_validation.get("actual_min_year"),
        "actual_end_year": result_validation.get("actual_end_year") or result_validation.get("actual_max_year"),
        "countries_present": result_validation.get("available_countries") or [],
        "countries_missing": result_validation.get("missing_countries") or [],
    }
    update_conversation_context(
        conversation_id,
        {
            "last_user_message": message,
            "last_answer": response.answer,
            "last_route": validated_query.get("route"),
            "last_status": response.status,
            "last_question_type": response.questionType,
            "last_parsed_query": asdict(candidate),
            "last_data_query": last_data_query,
            "last_validated_query": validated_query,
            "last_query_plan": _plan_to_dict(plan),
            "last_rows": row_summary["top_rows"],
            "last_chart": chart_without_data,
            "last_result_summary": last_result_summary,
            "last_chart_summary": chart_without_data,
            "last_result_validation": result_validation,
            "last_data_summary": {
                "indicator": validated_query.get("indicator"),
                "countries": validated_query.get("countries") or [],
                "years": [year for year in (validated_query.get("effective_start_year"), validated_query.get("effective_end_year")) if year],
                "start_year": validated_query.get("effective_start_year"),
                "end_year": validated_query.get("effective_end_year"),
                "limit": validated_query.get("limit"),
                "order": validated_query.get("ranking_order"),
                "row_count": row_summary["row_count"],
                "top_rows": row_summary["top_rows"],
            },
            "append_recent_turns": [
                make_user_turn(message),
                make_assistant_turn(response.answer, response.status, response.questionType, validated_query.get("route") or "DATA_QUERY"),
            ],
        },
    )
