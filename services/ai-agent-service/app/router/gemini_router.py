import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import asdict, dataclass, replace
from typing import Any

from app.core.config import settings
from app.composer.display_formatter import get_indicator_label
from app.llm.gemini_client import generate_gemini_text, is_gemini_enabled
from app.resolver.country_resolver import COUNTRIES, resolve_countries
from app.resolver.indicator_resolver import normalize_text


logger = logging.getLogger(__name__)

ROUTES = {
    "DATA_QUERY",
    "FOLLOW_UP_ANALYSIS",
    "FOLLOW_UP_MODIFY_QUERY",
    "DIRECT_ANSWER",
    "NEED_CLARIFICATION",
    "GENERAL_EXPLANATION",
    "UNSUPPORTED",
    "OFF_TOPIC",
}


@dataclass(frozen=True)
class RouterDecision:
    route: str
    confidence: float = 0.0
    needs_parser: bool = False
    needs_db: bool = False
    uses_previous_result: bool = False
    answer: str | None = None
    answer_strategy: str | None = None
    rewritten_query: str | None = None
    clarification_question: str | None = None
    reason: str | None = None
    source: str = "gemini_router"
    attempts: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def route_message(
    message: str,
    router_context: dict[str, Any] | None = None,
) -> RouterDecision:
    router_context = router_context or {}

    if not settings.gemini_router_enabled:
        return route_message_local_fallback(
            message,
            router_context,
            reason="gemini_router_disabled",
            attempts=0,
        )

    if not is_gemini_enabled():
        return route_message_local_fallback(
            message,
            router_context,
            reason="gemini_router_missing_api_key_or_disabled",
            attempts=0,
        )

    prompt = _build_router_prompt(message, router_context)
    max_attempts = max(1, 1 + max(settings.gemini_router_retries, 0))
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            text = _generate_with_timeout(prompt)
            decision = _parse_router_response(text, attempts=attempt)
            return _post_process_router_decision(message, router_context, decision)
        except Exception as error:
            last_error = error

            if _is_non_retryable_config_error(error):
                logger.warning("Gemini router non-retryable error: %s", error)
                return route_message_local_fallback(
                    message,
                    router_context,
                    reason=_config_error_reason(error),
                    attempts=attempt,
                )

            if attempt >= max_attempts:
                break

            if _should_retry(error):
                logger.warning("Gemini router attempt %s/%s failed, retrying: %s", attempt, max_attempts, error)
                _sleep_before_retry(attempt)
                continue

            break

    logger.warning("Gemini router failed after retries: %s", last_error)
    return route_message_local_fallback(
        message,
        router_context,
        reason="gemini_router_failed_after_retries",
        attempts=max_attempts,
    )


def route_message_local_fallback(
    message: str,
    router_context: dict[str, Any] | None = None,
    reason: str = "gemini_router_failed_after_retries",
    attempts: int = 0,
) -> RouterDecision:
    router_context = router_context or {}
    normalized = normalize_text(message)
    has_previous_result = _has_previous_result(router_context)

    if _is_followup_modify(normalized) and not _has_previous_query_context(router_context):
        return RouterDecision(
            route="NEED_CLARIFICATION",
            confidence=0.55,
            needs_parser=False,
            needs_db=False,
            uses_previous_result=False,
            clarification_question="Mình chưa có kết quả trước đó để chỉnh sửa. Bạn hãy gửi lại câu hỏi đầy đủ.",
            reason="missing_previous_query_context",
            source="local_router_fallback",
            attempts=attempts,
        )

    if _is_followup_modify(normalized) and has_previous_result:
        return RouterDecision(
            route="FOLLOW_UP_MODIFY_QUERY",
            confidence=0.55,
            needs_parser=True,
            needs_db=True,
            uses_previous_result=True,
            rewritten_query=_rewrite_followup_query(message, normalized, router_context),
            reason=reason,
            source="local_router_fallback",
            attempts=attempts,
        )

    if _is_followup_analysis(normalized) and has_previous_result:
        return RouterDecision(
            route="FOLLOW_UP_ANALYSIS",
            confidence=0.55,
            needs_parser=False,
            needs_db=False,
            uses_previous_result=True,
            answer=_local_contextual_followup_answer(router_context),
            answer_strategy="local_contextual_fallback",
            reason=reason,
            source="local_router_fallback",
            attempts=attempts,
        )

    if _is_direct_answer(normalized):
        return RouterDecision(
            route="GENERAL_EXPLANATION",
            confidence=0.45,
            needs_parser=False,
            needs_db=False,
            answer=_direct_answer_fallback(normalized),
            answer_strategy="local_definition_fallback",
            reason=reason,
            source="local_router_fallback",
            attempts=attempts,
        )

    if _is_unsupported(normalized):
        return RouterDecision(
            route="UNSUPPORTED",
            confidence=0.6,
            needs_parser=False,
            needs_db=False,
            reason=reason,
            source="local_router_fallback",
            attempts=attempts,
        )

    return RouterDecision(
        route="DATA_QUERY",
        confidence=0.0,
        needs_parser=True,
        needs_db=True,
        reason=reason,
        source="local_router_fallback",
        attempts=attempts,
    )


def _generate_with_timeout(prompt: str) -> str:
    timeout_seconds = max(settings.gemini_router_timeout_ms, 1) / 1000
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(
        generate_gemini_text,
        prompt,
        settings.gemini_router_model,
    )
    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeoutError as error:
        raise TimeoutError("Gemini router timeout") from error
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _build_router_prompt(message: str, router_context: dict[str, Any]) -> str:
    payload = {
        "current_message": message,
        "router_context": router_context,
        "allowed_routes": sorted(ROUTES),
    }
    return f"""
Bạn là lớp định tuyến và trả lời nhẹ cho một trợ lý phân tích dữ liệu kinh tế - xã hội.

Nhiệm vụ: phân loại message mới thành đúng route và trả về JSON duy nhất.

Luật output:
- Chỉ trả JSON object, không markdown, không code fence.
- Không bịa số liệu.
- Câu trả lời trong field answer phải viết trực tiếp cho người dùng.
- Không lộ thuật ngữ nội bộ trong answer: Gemini Router, router, parser, parsedQuery, AI Agent, AI Agent Service, database, DB, query planner, tool, model parser, ngrok, Kaggle.
- Nếu cần nói về dữ liệu, dùng "dữ liệu trước đó", "bảng kết quả trước đó" hoặc "kết quả đã hiển thị".
- DIRECT_ANSWER hoặc GENERAL_EXPLANATION: nếu hiểu câu hỏi thì answer phải có, không cần parser, không cần dữ liệu mới.
- FOLLOW_UP_ANALYSIS: nếu router_context có last_data_summary/top_rows/last_answer thì được phép trả answer dựa trên context, không gọi parser, không cần dữ liệu mới, không bịa số liệu mới.
- FOLLOW_UP_ANALYSIS: nếu nói nguyên nhân/vì sao, phải có câu "Đây là phân tích định tính, không phải bằng chứng nhân quả trực tiếp."
- FOLLOW_UP_ANALYSIS: nếu context không đủ, answer=null và answer_strategy="needs_composer_or_local_fallback".
- DATA_QUERY hoặc FOLLOW_UP_MODIFY_QUERY: không trả lời số liệu cụ thể nếu cần dữ liệu mới; answer=null.
- FOLLOW_UP_MODIFY_QUERY: rewritten_query phải là câu đầy đủ dựa trên query trước.

Routes:
- DIRECT_ANSWER: khái niệm, định nghĩa, cách hiểu chỉ số, cách dùng hệ thống; không cần dữ liệu mới.
- GENERAL_EXPLANATION: giải thích chung không cần dữ liệu mới.
- DATA_QUERY: số liệu cụ thể, ranking, top/bottom, so sánh quốc gia, xu hướng theo năm, coverage, anomaly, chart/table.
- FOLLOW_UP_ANALYSIS: user hỏi phân tích/nhận xét/giải thích kết quả trước; cần có previous result.
- FOLLOW_UP_MODIFY_QUERY: user sửa query trước như đổi năm, top N, thêm nước, đổi giai đoạn.
- NEED_CLARIFICATION: thiếu indicator/country/year quan trọng và chắc chắn cần hỏi lại.
- UNSUPPORTED: dự báo ML/ARIMA, train model, viết SQL, prediction tương lai, tác vụ ngoài phạm vi hỗ trợ hiện tại.
- OFF_TOPIC: ngoài phạm vi government/economic/social indicators.

JSON schema:
{{
  "route": "DATA_QUERY",
  "confidence": 0.0,
  "needs_parser": true,
  "needs_db": true,
  "uses_previous_result": false,
  "answer": null,
  "answer_strategy": null,
  "rewritten_query": null,
  "clarification_question": null,
  "reason": null
}}

Input:
{json.dumps(payload, ensure_ascii=False, default=str)}
""".strip()


def _parse_router_response(text: str, attempts: int = 1) -> RouterDecision:
    cleaned = _strip_code_fence(text)
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("Router response must be a JSON object")

    route = str(data.get("route") or "").upper()
    if route not in ROUTES:
        raise ValueError(f"Invalid router route: {route}")

    confidence = _clamp_float(data.get("confidence"), 0.0, 1.0)
    needs_parser = _bool_or_default(data.get("needs_parser"), route in {"DATA_QUERY", "FOLLOW_UP_MODIFY_QUERY"})
    needs_db = _bool_or_default(data.get("needs_db"), route in {"DATA_QUERY", "FOLLOW_UP_MODIFY_QUERY"})
    uses_previous_result = (
        True
        if route in {"FOLLOW_UP_ANALYSIS", "FOLLOW_UP_MODIFY_QUERY"}
        else _bool_or_default(data.get("uses_previous_result"), False)
    )

    if route in {"DATA_QUERY", "FOLLOW_UP_MODIFY_QUERY"}:
        answer = None
    else:
        answer = _optional_str(data.get("answer"))

    return RouterDecision(
        route=route,
        confidence=confidence,
        needs_parser=needs_parser,
        needs_db=needs_db,
        uses_previous_result=uses_previous_result,
        answer=answer,
        answer_strategy=_optional_str(data.get("answer_strategy")),
        rewritten_query=_optional_str(data.get("rewritten_query")),
        clarification_question=_optional_str(data.get("clarification_question")),
        reason=_optional_str(data.get("reason")),
        source="gemini_router",
        attempts=attempts,
    )


def _post_process_router_decision(
    message: str,
    router_context: dict[str, Any],
    decision: RouterDecision,
) -> RouterDecision:
    if decision.route != "FOLLOW_UP_MODIFY_QUERY":
        return decision

    if not _has_previous_query_context(router_context):
        return RouterDecision(
            route="NEED_CLARIFICATION",
            confidence=decision.confidence,
            needs_parser=False,
            needs_db=False,
            uses_previous_result=False,
            clarification_question="Mình chưa có kết quả trước đó để chỉnh sửa. Bạn hãy gửi lại câu hỏi đầy đủ.",
            reason="missing_previous_query_context",
            source=decision.source,
            attempts=decision.attempts,
        )

    normalized = normalize_text(message)
    rewritten_query = _rewrite_followup_query(message, normalized, router_context)
    if rewritten_query:
        return replace(decision, rewritten_query=rewritten_query)
    return decision


def _sleep_before_retry(attempt: int) -> None:
    backoff_seconds = max(settings.gemini_router_retry_backoff_ms, 0) / 1000
    time.sleep(backoff_seconds * (2 ** max(0, attempt - 1)))


def _should_retry(error: Exception) -> bool:
    if isinstance(error, (TimeoutError, json.JSONDecodeError, ValueError)):
        return True

    message = str(error).lower()
    retry_tokens = (
        "unavailable",
        "503",
        "429",
        "rate",
        "timeout",
        "temporarily",
        "temporary",
        "network",
        "connection",
        "dns",
        "deadline",
        "reset",
    )
    return any(token in message for token in retry_tokens)


def _is_non_retryable_config_error(error: Exception) -> bool:
    message = str(error).lower()
    if "disabled" in message or "api_key is missing" in message or "api key" in message:
        return True
    return "404" in message or "model not found" in message or "not found" in message


def _config_error_reason(error: Exception) -> str:
    message = str(error).lower()
    if "404" in message or "model not found" in message or "not found" in message:
        return "gemini_router_model_not_found"
    return "gemini_router_config_error"


def _has_previous_result(router_context: dict[str, Any]) -> bool:
    data_summary = router_context.get("last_data_summary") or {}
    return bool(
        router_context.get("last_rows")
        or data_summary.get("row_count")
        or router_context.get("last_parsed_query")
        or router_context.get("last_answer")
    )


def _has_previous_query_context(router_context: dict[str, Any]) -> bool:
    parsed_query = router_context.get("last_parsed_query") or {}
    data_summary = router_context.get("last_data_summary") or {}
    return bool(
        parsed_query.get("indicators")
        or parsed_query.get("unsupported_indicator")
        or data_summary.get("indicator")
        or router_context.get("last_rows")
    )


def _is_followup_analysis(normalized: str) -> bool:
    keywords = (
        "phan tich",
        "ly do",
        "tai sao",
        "giai thich",
        "nhan xet",
        "bang tren",
        "ket qua nay",
        "nuoc dung dau",
        "vi sao",
    )
    return any(keyword in normalized for keyword in keywords)


def _is_followup_modify(normalized: str) -> bool:
    explicit_keywords = (
        "doi sang",
        "lay top",
        "them",
        "add",
        "so sanh them",
        "chi lay",
        "giai doan",
        "remove",
        "bo ",
        "xoa ",
    )
    if any(keyword in normalized for keyword in explicit_keywords):
        return True

    return bool(re.search(r"\btop\s+\d+\b", normalized)) and "thoi" in normalized


def _is_direct_answer(normalized: str) -> bool:
    return any(
        keyword in normalized
        for keyword in (
            " la gi",
            "nghia la gi",
            "y nghia",
            "cach hieu",
            "giai thich chi so",
            "phan anh dieu gi",
            "dung de danh gia",
            "dung de hieu",
            "cho biet dieu gi",
            "khac gi",
        )
    )


def _is_unsupported(normalized: str) -> bool:
    return any(
        keyword in normalized
        for keyword in (
            "du bao",
            "forecast",
            "arima",
            "train model",
            "viet sql",
            "tu viet sql",
            "prediction",
        )
    )


def _rewrite_followup_query(
    message: str,
    normalized: str,
    router_context: dict[str, Any],
) -> str:
    base_query = router_context.get("last_user_message") or ""
    parsed_query = router_context.get("last_parsed_query") or {}
    data_summary = router_context.get("last_data_summary") or {}
    indicator_text = _indicator_text(parsed_query, base_query, data_summary)

    countries = _country_codes_from_context(parsed_query, data_summary)
    mentioned_countries = [match.country.code for match in resolve_countries(message)]
    if mentioned_countries:
        if _is_remove_country(normalized):
            countries = [code for code in countries if code not in mentioned_countries]
        elif _is_replace_field(normalized):
            countries = []
            for code in mentioned_countries:
                if code not in countries:
                    countries.append(code)
        else:
            for code in mentioned_countries:
                if code not in countries:
                    countries.append(code)
    country_text = _country_list_text(countries)

    years = [int(year) for year in re.findall(r"\b((?:19|20)\d{2})\b", normalized)]
    if len(years) >= 2:
        start_year, end_year = years[0], years[-1]
    elif len(years) == 1:
        start_year = end_year = years[0]
    else:
        start_year = parsed_query.get("start_year")
        end_year = parsed_query.get("end_year")
        summary_years = data_summary.get("years") or []
        if start_year is None and summary_years:
            start_year = min(summary_years)
        if end_year is None and summary_years:
            end_year = max(summary_years)

    limit_match = re.search(r"\btop\s+(\d+)\b", normalized)
    limit = int(limit_match.group(1)) if limit_match else parsed_query.get("limit") or data_summary.get("limit") or 10

    order = parsed_query.get("ranking_order") or data_summary.get("order") or "desc"
    if any(token in normalized for token in ("thap nhat", "lowest", "nho nhat")):
        order = "asc"
    elif any(token in normalized for token in ("cao nhat", "highest", "lon nhat")):
        order = "desc"
    order_text = "cao nhất" if order == "desc" else "thấp nhất"

    intent = parsed_query.get("intent") or ""
    base_is_ranking = intent == "RANKING" or "top" in normalize_text(base_query)
    if base_is_ranking:
        year = end_year or start_year
        return f"Top {limit} nước có {indicator_text} {order_text} năm {year}".strip()

    period_text = _period_text(start_year, end_year)
    if intent in {"TIME_SERIES", "TREND_ANALYSIS", "VALUE_LOOKUP"} or "xu huong" in normalize_text(base_query):
        return f"Xu hướng {indicator_text}{_of_country_text(country_text)} {period_text}".strip()

    if countries:
        return f"So sánh {indicator_text} của {country_text} {period_text}".strip()

    return f"{base_query} {message}".strip()


def _is_replace_field(normalized: str) -> bool:
    return any(token in normalized for token in ("doi sang", "thay bang", "thay thanh", "chuyen sang"))


def _is_remove_country(normalized: str) -> bool:
    return any(token in normalized for token in ("bo ", "xoa ", "loai ", "remove", "without"))


def _indicator_text(parsed_query: dict[str, Any], base_query: str, data_summary: dict[str, Any] | None = None) -> str:
    indicators = parsed_query.get("indicators") or []
    if not indicators and data_summary:
        indicator = data_summary.get("indicator")
        if indicator:
            indicators = [indicator]
    unsupported_indicator = parsed_query.get("unsupported_indicator")
    if not indicators and unsupported_indicator:
        return str(unsupported_indicator)
    normalized_base = normalize_text(base_query)
    if "inflation_cpi" in indicators or "lam phat" in normalized_base or "cpi" in normalized_base:
        return "lạm phát CPI"
    if "govdebt_GDP" in indicators or "no cong" in normalized_base:
        return "nợ công/GDP"
    if indicators:
        return get_indicator_label(str(indicators[0]))
    return "chỉ số"


def _country_codes_from_context(parsed_query: dict[str, Any], data_summary: dict[str, Any]) -> list[str]:
    codes: list[str] = []
    for value in parsed_query.get("countries") or data_summary.get("countries") or []:
        code = str(value).upper()
        if code and code not in codes:
            codes.append(code)
    return codes


def _country_list_text(country_codes: list[str]) -> str:
    labels = [COUNTRIES.get(code).name if COUNTRIES.get(code) else code for code in country_codes]
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + " và " + labels[-1]


def _period_text(start_year: Any, end_year: Any) -> str:
    if start_year and end_year:
        if start_year == end_year:
            return f"năm {start_year}"
        return f"từ {start_year} đến {end_year}"
    if start_year:
        return f"từ {start_year}"
    if end_year:
        return f"đến {end_year}"
    return ""


def _of_country_text(country_text: str) -> str:
    return f" của {country_text}" if country_text else ""


def _direct_answer_fallback(normalized: str) -> str:
    if "gdp per capita" in normalized or "binh quan dau nguoi" in normalized or "income per capita" in normalized:
        return "GDP per capita là GDP bình quân đầu người: GDP tổng chia cho dân số. Trong dữ liệu hiện có, chỉ số gần nhất là GDP thực bình quân đầu người ở dạng log, nên giá trị dùng để so sánh là thang log chứ không phải USD trực tiếp."
    if "trade openness" in normalized or "do mo thuong mai" in normalized:
        return "Trade openness là tỷ lệ tổng thương mại so với GDP. Chỉ số này thường cho biết nền kinh tế phụ thuộc nhiều hay ít vào trao đổi hàng hóa và dịch vụ với bên ngoài."

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

    if "poverty headcount" in normalized or "ty le ngheo" in normalized:
        return (
            "Poverty headcount là tỷ lệ dân số sống dưới ngưỡng nghèo. "
            "Chỉ số này thường dùng để đánh giá mức độ nghèo đói và khả năng bao phủ "
            "của tăng trưởng, việc làm và chính sách an sinh đối với người dân."
        )

    if "reer deviation" in normalized or "do lech reer" in normalized:
        return (
            "REER deviation là độ lệch của tỷ giá hiệu dụng thực so với xu hướng hoặc mức tham chiếu. "
            "Chỉ số này giúp nhận diện áp lực mất cân đối tỷ giá, khả năng đồng tiền bị định giá cao/thấp "
            "và rủi ro cạnh tranh bên ngoài."
        )

    if "fiscal balance" in normalized or "budget balance" in normalized or "can can ngan sach" in normalized:
        return "Fiscal balance/GDP là cán cân ngân sách so với GDP. Giá trị dương thường là thặng dư ngân sách, còn giá trị âm thường là thâm hụt ngân sách."
    if "gfcf" in normalized or "gross fixed capital formation" in normalized or "dau tu co dinh" in normalized:
        return "GFCF to GDP là đầu tư cố định gộp so với GDP, phản ánh phần sản lượng được dành cho tài sản cố định như máy móc, nhà xưởng và hạ tầng."
    if "real interest rate" in normalized or "lai suat thuc" in normalized:
        return "Real interest rate là lãi suất thực sau khi điều chỉnh lạm phát, giúp nhìn chi phí vay hoặc lợi suất tiết kiệm theo sức mua thực tế."
    if "coverage" in normalized:
        return "Coverage dữ liệu cho biết một chỉ số có dữ liệu ở những quốc gia, năm bắt đầu, năm kết thúc và số quan sát nhiều hay ít."
    if "no cong" in normalized or "public debt" in normalized or "government debt" in normalized:
        return (
            "Nợ công/GDP là tỷ lệ nợ công so với GDP, dùng để đánh giá quy mô nợ của khu vực công "
            "so với quy mô nền kinh tế."
        )
    if "lam phat cpi" in normalized or "cpi" in normalized:
        return (
            "Lạm phát CPI là mức tăng của chỉ số giá tiêu dùng, phản ánh thay đổi giá của rổ hàng hóa "
            "và dịch vụ tiêu dùng theo thời gian."
        )
    if "that nghiep" in normalized or "unemployment" in normalized:
        return "Tỷ lệ thất nghiệp phản ánh phần lực lượng lao động đang không có việc làm nhưng có nhu cầu và sẵn sàng làm việc."
    if "tax revenue" in normalized or "thu thue" in normalized:
        return "Tax revenue/GDP là thu thuế so với GDP, thường dùng để đánh giá năng lực huy động nguồn thu thuế của một nền kinh tế."
    return "Đây là câu hỏi giải thích khái niệm, không cần dữ liệu mới. Bạn có thể nêu rõ chỉ số để mình giải thích cụ thể hơn."


def _local_contextual_followup_answer(router_context: dict[str, Any]) -> str:
    data_summary = router_context.get("last_data_summary") or {}
    row_count = data_summary.get("row_count")
    indicator = get_indicator_label(data_summary.get("indicator")) if data_summary.get("indicator") else "chỉ số đang xét"
    years = data_summary.get("years") or []
    top_rows = data_summary.get("top_rows") or router_context.get("last_rows") or []

    scope_parts = []
    if row_count:
        scope_parts.append(f"{row_count} dòng kết quả")
    if years:
        scope_parts.append(f"giai đoạn/năm {', '.join(str(year) for year in years[:3])}")
    scope = " trong " + ", ".join(scope_parts) if scope_parts else ""

    leading = ""
    if top_rows:
        leading = " Các kết quả nổi bật trong bảng trước đó có thể phản ánh khác biệt về bối cảnh kinh tế, chính sách và chất lượng dữ liệu giữa các nước."

    return (
        f"Dựa trên kết quả đã hiển thị cho {indicator}{scope}, mình có thể đưa ra nhận xét định tính ở mức tổng quát."
        f"{leading} Đây là phân tích định tính, không phải bằng chứng nhân quả trực tiếp."
    )


def _strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return cleaned


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _bool_or_default(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _clamp_float(value: Any, min_value: float, max_value: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = min_value
    return max(min_value, min(max_value, number))
