import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class _Settings:
    postgres_host:     str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port:     str = os.getenv("POSTGRES_PORT", "5432")
    postgres_db:       str = os.getenv("POSTGRES_DB", "")
    postgres_user:     str = os.getenv("POSTGRES_USER", "")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "")


settings = _Settings()
