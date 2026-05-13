from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Government AI Agent Service"
    app_env: str = "development"
    app_version: str = "0.1.0"

    host: str = "0.0.0.0"
    port: int = 8002

    internal_api_key: str = "dev-internal-key"

    database_url: str | None = None

    pipeline_mode: str = "hybrid_v2"
    enable_hybrid_v2_fallback: bool = False
    hybrid_v2_debug: bool = True

    enable_rule_first_router: bool = True
    enable_front_llm_router: bool = True
    enable_parser_agent: bool = True
    enable_db_truth_validator: bool = True
    enable_result_validator: bool = True
    enable_deterministic_data_composer: bool = True
    enable_gemini_numeric_composer: bool = False

    canonical_catalog_version: str = "canonical_db_v1"

    enable_gemini: bool = False
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.1-flash-lite-preview"
    gemini_router_enabled: bool = True
    gemini_router_model: str = "gemini-3.1-flash-lite-preview"
    gemini_router_timeout_ms: int = 10000
    gemini_router_retries: int = 1
    gemini_router_retry_backoff_ms: int = 700
    gemini_composer_enabled: bool = True
    conversation_context_max_rows: int = 20

    parser_service_base_url: str | None = None
    parser_service_timeout_ms: int = 30000
    parser_mode: str = "hybrid"
    parser_debug: bool = False
    parser_hybrid_allowed_intents: str = (
        "COMPARE_COUNTRIES,RANKING,TIME_SERIES,TREND_ANALYSIS,VALUE_LOOKUP,"
        "COVERAGE,RANK_BY_CHANGE,COMPARE_INDICATORS,ANOMALY_DETECTION,"
        "NEED_CLARIFICATION,UNSUPPORTED,OFF_TOPIC"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
