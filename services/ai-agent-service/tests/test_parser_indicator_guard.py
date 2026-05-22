from __future__ import annotations

from app.core.config import settings
from app.parser.hybrid_parser import parse_with_hybrid_parser


def _mock_parser_response(indicators: list[str]) -> dict:
    return {
        "parsed": {
            "intent": "TIME_SERIES",
            "indicators": indicators,
            "countries": ["VNM", "THA"],
            "start_year": 2010,
            "end_year": 2023,
        },
        "safe_to_execute": True,
        "catalog_pass": True,
        "deployment_schema_pass": True,
        "schema_pass": True,
    }


def test_parser_flag_score_indicator_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(settings, "parser_mode", "hybrid")
    monkeypatch.setattr(
        "app.parser.hybrid_parser.call_parser_service",
        lambda message, context=None: _mock_parser_response(["flag_score"]),
    )

    result = parse_with_hybrid_parser("so sánh flag_score của VNM và THA")

    assert result.question_type == "UNSUPPORTED_DATA_QUERY"
    assert result.plan.tool_name == "none"
    assert result.status == "unsupported"
    assert result.parser_debug["indicator_guard"]["forbidden_indicators"] == ["flag_score"]


def test_parser_decade_indicator_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(settings, "parser_mode", "hybrid")
    monkeypatch.setattr(
        "app.parser.hybrid_parser.call_parser_service",
        lambda message, context=None: _mock_parser_response(["decade"]),
    )

    result = parse_with_hybrid_parser("xu hướng decade của VNM")

    assert result.question_type == "UNSUPPORTED_DATA_QUERY"
    assert result.plan.tool_name == "none"
    assert result.status == "unsupported"
    assert result.parser_debug["indicator_guard"]["forbidden_indicators"] == ["decade"]


def test_valid_parser_output_still_builds_compare_plan(monkeypatch) -> None:
    monkeypatch.setattr(settings, "parser_mode", "hybrid")
    monkeypatch.setattr(
        "app.parser.hybrid_parser.call_parser_service",
        lambda message, context=None: _mock_parser_response(["govdebt_GDP"]),
    )

    result = parse_with_hybrid_parser("so sánh nợ công Việt Nam và Thái Lan từ 2010 đến 2023")

    assert result.question_type == "VALID_TREND_QUERY"
    assert result.plan.tool_name in {"get_indicator_series", "get_indicator_analytics_series"}
    assert result.plan.arguments["indicator_code"] == "govdebt_GDP"
    assert result.plan.arguments["country_codes"] == ["VNM", "THA"]
    assert result.plan.arguments["start_year"] == 2010
    assert result.plan.arguments["end_year"] == 2023
