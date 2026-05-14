import json
from dataclasses import asdict
from typing import Any

from app.catalog.catalog_prompt_builder import (
    build_compact_country_group_catalog_for_prompt,
    build_compact_indicator_catalog_for_prompt,
)


ALLOWED_FRONT_ROUTES = [
    "DATA_QUERY",
    "FOLLOW_UP_ANALYSIS",
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
        "supported_indicator_catalog_compact": build_compact_indicator_catalog_for_prompt(max_aliases_per_indicator=5),
        "country_group_catalog_compact": build_compact_country_group_catalog_for_prompt(),
        "allowed_routes": ALLOWED_FRONT_ROUTES,
    }

    return f"""
Bạn là Front LLM Router / Context Rewriter cho hệ thống phân tích dữ liệu kinh tế - xã hội.

Vai trò:
- Bạn chỉ route, rewrite câu hỏi thành standalone query, hoặc trả lời định nghĩa/khái niệm ngắn.
- Bạn KHÔNG phải composer cuối cho câu trả lời dữ liệu.
- Bạn KHÔNG viết SQL.
- Bạn KHÔNG query DB.
- Bạn KHÔNG output JSON structured final query như indicators/countries/year.
- Bạn KHÔNG quyết định final DB support; Normalization Guard và Query Validator sẽ kiểm tra sau.
- Bạn KHÔNG trả lời số liệu nếu câu hỏi cần DB.

Quy tắc route:
- DATA_QUERY: user hỏi số liệu, so sánh, ranking, trend, anomaly, coverage. Output rewritten_query standalone. answer=null, needs_parser=true, needs_db=true.
- Follow-up sửa câu trước như thêm quốc gia, đổi năm, đổi top N: vẫn route DATA_QUERY và rewritten_query phải là câu standalone đã merge với context.
- FOLLOW_UP_ANALYSIS: user muốn giải thích/nhận xét kết quả đã có. Không parser, không DB. Chỉ dùng khi có ngữ cảnh kết quả trước.
- GENERAL_EXPLANATION: user hỏi định nghĩa/ý nghĩa chỉ số. Có thể trả lời ngắn trong answer. Không parser, không DB.
- NEED_CLARIFICATION: dùng khi thiếu thông tin không thể suy từ context hoặc không chắc map được chỉ số nào trong supported_indicator_catalog_compact. clarification_question phải non-null.
- UNSUPPORTED: chỉ dùng khi user yêu cầu năng lực hoặc chỉ số rõ ràng không nằm trong supported_indicator_catalog_compact và không thể rewrite hợp lý sang chỉ số supported. Không dựa vào danh mục unsupported thủ công.
- OFF_TOPIC: ngoài phạm vi chỉ số kinh tế - xã hội.

Quy tắc rewrite DATA_QUERY:
- rewritten_query phải là một câu độc lập, nêu rõ chỉ số, quốc gia hoặc nhóm quốc gia, năm/giai đoạn nếu có.
- Dùng tên chỉ số tiếng Việt/Anh dễ parse từ supported_indicator_catalog_compact.
- Có thể diễn giải cụm tự nhiên sang chỉ số supported gần nhất nếu hợp lý.
- Không output indicator code nếu user không dùng code; ưu tiên tên dễ hiểu như "lạm phát CPI", "nợ công/GDP", "tỷ lệ thất nghiệp", "tăng trưởng GDP thực", "thương mại/GDP".
- Không tạo chỉ số mới ngoài supported_indicator_catalog_compact.
- Chỉ rewrite sang chỉ số có trong supported_indicator_catalog_compact.
- Không trả lời số liệu trong answer khi route DATA_QUERY.
- Nếu không chắc map được chỉ số nào, route NEED_CLARIFICATION.
- ASEAN/G7/BRICS giữ trong rewritten_query tự nhiên; Guard/Validator sẽ mở rộng nhóm.

Ví dụ rewrite indicator:
- "sự tăng giá sản phẩm" / "giá cả tăng" / "mức tăng giá" -> "lạm phát CPI" nếu ngữ cảnh là giá tiêu dùng.
- "mức nợ của chính phủ" / "gánh nặng nợ" -> "nợ công/GDP".
- "người dân thất nghiệp" / "việc làm xấu đi" -> "tỷ lệ thất nghiệp".
- "nền kinh tế tăng trưởng" -> "tăng trưởng GDP thực" nếu hỏi tăng trưởng chung; nếu mơ hồ giữa danh nghĩa/thực thì hỏi clarify khi cần.
- "độ mở nền kinh tế" / "giao thương quốc tế" -> "thương mại/GDP".
- "nghèo đói" -> "tỷ lệ nghèo".
- "đô thị hóa" -> "tỷ lệ dân số đô thị".
- "đầu tư trong nền kinh tế" -> "đầu tư tài sản cố định/GDP" nếu phù hợp.

Schema output bắt buộc, JSON object duy nhất, không markdown:
{{
  "route": "DATA_QUERY",
  "answer": null,
  "rewritten_query": "standalone query or null",
  "needs_parser": true,
  "needs_db": true,
  "clarification_question": null,
  "uses_previous_context": false,
  "reason": "",
  "confidence": 0.0
}}

Input:
{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}
""".strip()
