from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.core.config import settings


_engine: Engine | None = None


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


def get_postgres_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_postgres_engine()
    return _engine
