import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _default_run_id() -> str:
    return _utc_now().strftime("manual-%Y%m%dT%H%M%SZ")


def _default_run_date() -> str:
    return _utc_now().strftime("%Y-%m-%d")


def _get_output_format() -> str:
    value = os.getenv("OUTPUT_FORMAT", "csv").strip().lower()
    allowed = {"csv", "parquet"}

    if value not in allowed:
        raise ValueError(
            f"Invalid OUTPUT_FORMAT={value!r}. Expected one of: {sorted(allowed)}"
        )

    return value


@dataclass(frozen=True)
class _Settings:
    postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port: str = os.getenv("POSTGRES_PORT", "5432")
    postgres_db: str = os.getenv("POSTGRES_DB", "")
    postgres_user: str = os.getenv("POSTGRES_USER", "")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "")

    run_id: str = field(default_factory=lambda: os.getenv("RUN_ID") or _default_run_id())
    run_date: str = field(default_factory=lambda: os.getenv("RUN_DATE") or _default_run_date())

    output_format: str = field(default_factory=_get_output_format)
    silver_output_uri: str = os.getenv(
        "SILVER_OUTPUT_URI",
        "/opt/workspace/data/processed_data/processed.csv",
    )
    source_registry_path: str = os.getenv(
        "SOURCE_REGISTRY_PATH",
        str(Path(__file__).with_name("source_registry.yaml")),
    )


settings = _Settings()
