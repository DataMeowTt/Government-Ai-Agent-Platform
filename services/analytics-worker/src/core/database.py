from sqlalchemy import create_engine
from src.core.config import settings

_engine = None


def get_engine():
    global _engine

    if _engine is not None:
        return _engine

    if not settings.DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not configured. Set DATABASE_URL for live analytics runs "
            "or use --dry-run for offline planning."
        )

    _engine = create_engine(
        settings.DATABASE_URL,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_pre_ping=True,
        pool_recycle=1800,
    )
    return _engine
