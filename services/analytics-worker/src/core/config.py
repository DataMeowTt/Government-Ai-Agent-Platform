from datetime import UTC, datetime
import os
from uuid import uuid4

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ModuleNotFoundError:
    BaseSettings = object
    SettingsConfigDict = None


if SettingsConfigDict:
    class Settings(BaseSettings):
        DATABASE_URL: str | None = None
        WORKER_PORT: int = 8001
        ENVIRONMENT: str = "development"
        RUN_ID: str = f"analytics-{uuid4()}"
        RUN_DATE: str = datetime.now().date().isoformat()
        BIGQUERY_ANALYTICS_DATASET: str = "gov_ai_analytics"
        BIGQUERY_LOCATION: str = "asia-southeast1"
        ANALYTICS_LATEST_VALID_YEAR: int | None = None

        model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
else:
    class Settings:
        def __init__(self):
            self.DATABASE_URL = os.getenv("DATABASE_URL")
            self.WORKER_PORT = int(os.getenv("WORKER_PORT", "8001"))
            self.ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
            self.RUN_ID = os.getenv("RUN_ID", f"analytics-{uuid4()}")
            self.RUN_DATE = os.getenv("RUN_DATE", datetime.now().date().isoformat())
            self.BIGQUERY_ANALYTICS_DATASET = os.getenv(
                "BIGQUERY_ANALYTICS_DATASET",
                "gov_ai_analytics",
            )
            self.BIGQUERY_LOCATION = os.getenv("BIGQUERY_LOCATION", "asia-southeast1")
            raw_latest_year = os.getenv("ANALYTICS_LATEST_VALID_YEAR")
            self.ANALYTICS_LATEST_VALID_YEAR = int(raw_latest_year) if raw_latest_year else None

settings = Settings()


def get_loaded_at() -> str:
    return datetime.now(UTC).isoformat()


def get_runtime_metadata() -> dict[str, str]:
    return {
        "run_id": settings.RUN_ID,
        "run_date": settings.RUN_DATE,
        "loaded_at": get_loaded_at(),
    }
