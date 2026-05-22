import sys
import types
import importlib.util
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))


if importlib.util.find_spec("pydantic_settings") is None:
    pydantic_settings = types.ModuleType("pydantic_settings")

    class BaseSettings:
        def __init__(self, **kwargs):
            for name, value in self.__class__.__dict__.items():
                if not name.startswith("_") and not callable(value):
                    setattr(self, name, value)
            for name, value in kwargs.items():
                setattr(self, name, value)

    def SettingsConfigDict(**kwargs):
        return dict(kwargs)

    pydantic_settings.BaseSettings = BaseSettings
    pydantic_settings.SettingsConfigDict = SettingsConfigDict
    sys.modules["pydantic_settings"] = pydantic_settings


from app.conversation.followup_merge import merge_followup_query  # noqa: E402
from app.catalog.canonical_indicator_catalog import resolve_indicator_aliases  # noqa: E402
from app.catalog.indicator_catalog import get_indicator  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.parser.parser_agent import run_parser_agent  # noqa: E402
from app.pipeline.schemas import ParsedQueryCandidate  # noqa: E402
from app.router.rule_first_router import run_rule_first_router  # noqa: E402
from app.schemas.chat import AiAgentMetadata  # noqa: E402
from app.tools.common import indicator_column_name  # noqa: E402
from app.validator.query_validator import validate_parsed_candidate  # noqa: E402
from app.validator.result_validator import validate_tool_result  # noqa: E402


def main() -> None:
    agent_source = (SERVICE_ROOT / "app" / "routers" / "agent.py").read_text(encoding="utf-8")
    runner_source = (SERVICE_ROOT / "app" / "pipeline" / "hybrid_v2_runner.py").read_text(encoding="utf-8")
    assert 'settings.pipeline_mode.lower() == "hybrid_v2"' in agent_source
    assert "settings.enable_hybrid_v2_fallback" in agent_source
    assert "logger.exception" in runner_source
    assert "settings.enable_hybrid_v2_fallback" in runner_source
    assert '"pipeline": "hybrid_v2"' in runner_source

    assert hasattr(settings, "pipeline_mode")
    assert hasattr(settings, "enable_hybrid_v2_fallback")
    assert hasattr(settings, "hybrid_v2_debug")
    metadata = AiAgentMetadata(pipeline="hybrid_v2", fallbackUsed=False)
    assert metadata.pipeline == "hybrid_v2"
    assert metadata.fallbackUsed is False
    assert indicator_column_name(get_indicator("trade_pct_gdp")) == "trade_pct_gdp"
    assert indicator_column_name(get_indicator("log_rGDP_pc_USD")) == "log_rGDP_pc_USD"
    assert resolve_indicator_aliases("GDP per capita", limit=0) == []

    context = {"last_answer": "...", "last_rows": [{"year": 2020}]}
    followup = run_rule_first_router("Giải thích kết quả này ngắn gọn", context)
    assert followup.route == "FOLLOW_UP_ANALYSIS"
    assert followup.needs_db is False
    assert followup.needs_parser_agent is False

    coverage = run_rule_first_router("Coverage dữ liệu nợ công/GDP của Việt Nam")
    assert coverage.intent_hint == "COVERAGE"
    assert "govdebt_GDP" in coverage.draft_indicators

    unsupported = run_rule_first_router("So sánh current account/GDP của Việt Nam và Philippines")
    assert unsupported.unsupported_terms
    assert unsupported.needs_db is False

    gdp_candidate = run_parser_agent(
        user_message="So sánh GDP per capita của Brazil và Mexico từ 2000 đến 2022",
        conversation_context=None,
        rule_draft=None,
        front_draft=None,
        model_parsed={"intent": "NEED_CLARIFICATION", "indicators": []},
    )
    assert "log_rGDP_pc_USD" in gdp_candidate.indicators
    assert gdp_candidate.intent != "NEED_CLARIFICATION"

    trade_candidate = run_parser_agent(
        user_message="So sánh trade openness của Việt Nam và Malaysia từ 2010 đến 2022",
        conversation_context=None,
        rule_draft=None,
        front_draft=None,
    )
    assert "trade_pct_gdp" in trade_candidate.indicators

    unsupported_candidate = ParsedQueryCandidate(
        route="DATA_QUERY",
        intent="UNSUPPORTED",
        indicators=[],
        countries=["VNM"],
        unsupported_terms=["current_account_GDP"],
        source="test",
        confidence=1.0,
        reason="test",
    )
    unsupported_validation = validate_parsed_candidate(unsupported_candidate)
    assert unsupported_validation.status == "unsupported"

    valid_trade = validate_parsed_candidate(
        ParsedQueryCandidate(
            route="DATA_QUERY",
            intent="COMPARE_COUNTRIES",
            indicators=["trade_pct_gdp"],
            countries=["VNM", "MYS"],
            country_groups=[],
            start_year=2010,
            end_year=2022,
            source="test",
            confidence=1.0,
            reason="test",
        )
    )
    assert valid_trade.ok is True
    assert valid_trade.question_type == "VALID_COMPARE_QUERY"

    coverage_asean = validate_parsed_candidate(
        ParsedQueryCandidate(
            route="DATA_QUERY",
            intent="COVERAGE",
            indicators=["unemployment_total"],
            countries=[],
            country_groups=["ASEAN"],
            source="test",
            confidence=1.0,
            reason="test",
        )
    )
    assert coverage_asean.ok is True
    countries = coverage_asean.validated_query["countries"]
    for code in ("VNM", "THA", "IDN", "MYS", "PHL"):
        assert code in countries

    result_validation = validate_tool_result(
        rows=[{"country_code": "IDN", "year": 2020, "value": 1.2}],
        validated_query={
            "countries": ["IND", "IDN"],
            "effective_start_year": 2010,
            "effective_end_year": 2022,
        },
    )
    assert "IND" in result_validation.missing_countries
    assert result_validation.is_partial is True

    merged = merge_followup_query(
        previous_query={
            "intent": "RANKING",
            "indicator": "trade_pct_gdp",
            "indicators": ["trade_pct_gdp"],
            "start_year": 2021,
            "end_year": 2021,
            "limit": 10,
            "ranking_order": "desc",
        },
        delta={"limit": 5, "ranking_order": "asc"},
    )
    assert merged["limit"] == 5
    assert merged["ranking_order"] == "asc"
    assert merged["indicator"] == "trade_pct_gdp"

    print("pipeline v2 unit checks passed")


if __name__ == "__main__":
    main()
