import json
from dataclasses import asdict
from typing import Any

from app.catalog.catalog_prompt_builder import (
    build_compact_country_catalog_for_prompt,
    build_compact_country_group_catalog_for_prompt,
    build_compact_indicator_catalog_for_prompt,
    build_compact_unsupported_indicator_catalog_for_prompt,
)


ALLOWED_FRONT_ROUTES = [
    "DATA_QUERY",
    "FOLLOW_UP_ANALYSIS",
    "FOLLOW_UP_MODIFY_QUERY",
    "DIRECT_ANSWER",
    "GENERAL_EXPLANATION",
    "NEED_CLARIFICATION",
    "UNSUPPORTED",
    "OFF_TOPIC",
]

ALLOWED_FRONT_INTENTS = [
    "COMPARE_COUNTRIES",
    "RANKING",
    "TIME_SERIES",
    "TREND_ANALYSIS",
    "ANOMALY_DETECTION",
    "COVERAGE",
    "VALUE_LOOKUP",
    "NEED_CLARIFICATION",
    "UNSUPPORTED",
    "OFF_TOPIC",
    "DIRECT_ANSWER",
    "GENERAL_EXPLANATION",
]


def build_front_router_prompt(
    user_message: str,
    conversation_context: dict[str, Any],
    rule_route_draft: Any | None = None,
) -> str:
    payload = {
        "user_message": user_message,
        "conversation_context": conversation_context,
        "rule_route_draft": asdict(rule_route_draft) if rule_route_draft else None,
        "supported_indicator_catalog_compact": build_compact_indicator_catalog_for_prompt(max_aliases_per_indicator=8),
        "unsupported_indicator_catalog_compact": build_compact_unsupported_indicator_catalog_for_prompt(),
        "country_catalog_compact": build_compact_country_catalog_for_prompt(max_aliases_per_country=6),
        "country_group_catalog_compact": build_compact_country_group_catalog_for_prompt(),
        "allowed_routes": ALLOWED_FRONT_ROUTES,
        "allowed_intents": ALLOWED_FRONT_INTENTS,
    }

    return f"""
Bạn là lớp Front LLM Router / Context Rewriter cho hệ thống phân tích dữ liệu kinh tế - xã hội.

Bạn KHÔNG phải composer cuối.
Bạn KHÔNG được viết SQL.
Bạn KHÔNG được trả lời số liệu.
Bạn KHÔNG được tự tạo indicator code ngoài supported_indicator_catalog_compact.
Bạn KHÔNG được quyết định support cuối cùng; validator DB-truth sẽ quyết định cuối.
Nếu có rule_route_draft, hãy dùng nó như tín hiệu gợi ý. Nếu rule confidence cao và hợp lý, ưu tiên giữ route/slots của rule.

Nhiệm vụ:
1. Xác định route sơ bộ.
2. Nếu là follow-up, dùng conversation_context để rewrite hoặc tạo draft.
3. Nếu là data query mới, trích xuất draft intent/indicator/country/year nếu thấy rõ.
4. Chỉ chọn indicator code có trong supported_indicator_catalog_compact.
5. Chỉ chọn country code có trong country_catalog_compact.
6. Nếu user hỏi chỉ số không có trong supported catalog nhưng có trong unsupported catalog, đưa vào unsupported_terms.
7. Nếu thiếu slot quan trọng, route NEED_CLARIFICATION.
8. Output JSON object duy nhất, không markdown, không code fence.

Schema output bắt buộc:
{{
  "route": "DATA_QUERY",
  "intent_hint": "COMPARE_COUNTRIES",
  "rewritten_query": null,
  "draft_indicators": [],
  "draft_countries": [],
  "draft_country_groups": [],
  "draft_start_year": null,
  "draft_end_year": null,
  "draft_limit": null,
  "draft_ranking_order": null,
  "unsupported_terms": [],
  "clarification_questions": [],
  "uses_previous_context": false,
  "confidence": 0.0,
  "reason": ""
}}

Quy tắc:
- FOLLOW_UP_ANALYSIS: người dùng hỏi giải thích/nhận xét/phân tích kết quả trước, không cần query DB mới.
- FOLLOW_UP_MODIFY_QUERY: người dùng sửa câu hỏi trước như đổi năm, thêm nước, top N, cao nhất/thấp nhất.
- DATA_QUERY: hỏi số liệu, so sánh, ranking, trend, anomaly, coverage.
- NEED_CLARIFICATION: thiếu indicator/country/year bắt buộc và không đủ context để merge.
- UNSUPPORTED: yêu cầu ngoài khả năng hoặc chỉ số không có trong catalog.
- OFF_TOPIC: ngoài phạm vi kinh tế - xã hội/chỉ số dữ liệu.
- current account/GDP và external debt/GNI là unsupported nếu xuất hiện.
- trade openness phải map về trade_pct_gdp.
- GDP per capita phải map về log_rGDP_pc_USD.
- ASEAN/G7 đưa vào draft_country_groups, không tự mở rộng countries.

Input:
{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}
""".strip()
