from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from config.settings import settings


def get_engine() -> Engine:
    url = (
        f"postgresql+psycopg2://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )
    return create_engine(url)


def test_connection() -> None:
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("Connection OK")


if __name__ == "__main__":
    print("Testing Postgres connection...")
    test_connection()
