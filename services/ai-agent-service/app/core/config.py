from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Government AI Agent Service"
    app_env: str = "development"
    app_version: str = "0.1.0"

    host: str = "0.0.0.0"
    port: int = 8002

    internal_api_key: str = "dev-internal-key"

    database_url: str | None = None

    enable_gemini: bool = False
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"

    parser_service_base_url: str | None = None
    parser_service_timeout_ms: int = 30000
    parser_mode: str = "hybrid"
    parser_debug: bool = False
    parser_hybrid_allowed_intents: str = (
        "COMPARE_COUNTRIES,RANKING,TIME_SERIES,TREND_ANALYSIS,VALUE_LOOKUP,"
        "COVERAGE,RANK_BY_CHANGE,COMPARE_INDICATORS,ANOMALY_DETECTION"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
