from sqlalchemy import bindparam, text

from app.db.postgres import engine
from app.tools.common import (
    indicator_column_name,
    normalize_country_codes,
    quote_identifier,
    require_indicator,
    rows_to_dicts,
)


def rank_countries(
    indicator_code: str,
    year: int,
    limit: int = 10,
    order: str = "desc",
    country_codes: list[str] | None = None,
) -> list[dict]:
    indicator = require_indicator(indicator_code)

    table_name = indicator.gold_table
    column_name = quote_identifier(indicator_column_name(indicator))

    safe_limit = max(1, min(int(limit or 10), 50))
    direction = "ASC" if str(order).lower() == "asc" else "DESC"
    countries = normalize_country_codes(country_codes)

    conditions = [
        "year = :year",
        f"{column_name} IS NOT NULL",
    ]
    params: dict = {
        "year": year,
        "limit": safe_limit,
    }

    if countries:
        conditions.append("country_code IN :country_codes")
        params["country_codes"] = countries

    where_sql = " AND ".join(conditions)

    sql = text(
        f"""
        SELECT
            country_code,
            country,
            year,
            {column_name} AS value
        FROM {table_name}
        WHERE {where_sql}
        ORDER BY value {direction}
        LIMIT :limit
        """
    )

    if countries:
        sql = sql.bindparams(bindparam("country_codes", expanding=True))

    with engine.connect() as conn:
        rows = conn.execute(sql, params).fetchall()

    return rows_to_dicts(rows)