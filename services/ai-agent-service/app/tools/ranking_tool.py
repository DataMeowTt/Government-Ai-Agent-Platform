from sqlalchemy import text

from app.db.postgres import engine
from app.tools.common import quote_identifier, require_indicator, rows_to_dicts


def rank_countries(
    indicator_code: str,
    year: int,
    limit: int = 10,
    order: str = "desc",
) -> list[dict]:
    indicator = require_indicator(indicator_code)

    table_name = indicator.gold_table
    column_name = quote_identifier(indicator.code)

    safe_limit = max(1, min(limit, 50))
    direction = "ASC" if order.lower() == "asc" else "DESC"

    sql = text(
        f"""
        SELECT
            country_code,
            country,
            year,
            {column_name} AS value
        FROM {table_name}
        WHERE year = :year
          AND {column_name} IS NOT NULL
        ORDER BY value {direction}
        LIMIT :limit
        """
    )

    with engine.connect() as conn:
        rows = conn.execute(
            sql,
            {
                "year": year,
                "limit": safe_limit,
            },
        ).fetchall()

    return rows_to_dicts(rows)