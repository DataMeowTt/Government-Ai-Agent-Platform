from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.core.config import settings


def create_postgres_engine() -> Engine:
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not configured")

    return create_engine(
        settings.database_url,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_pre_ping=True,
        pool_recycle=1800,
    )


engine = create_postgres_engine()