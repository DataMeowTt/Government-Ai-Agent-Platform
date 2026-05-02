from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Government AI Agent Service"
    app_env: str = "development"
    app_version: str = "0.1.0"

    host: str = "0.0.0.0"
    port: int = 8002

    internal_api_key: str = "dev-internal-key"

    database_url: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()