from sqlalchemy import bindparam, text

from app.db.postgres import engine
from app.tools.common import (
    normalize_country_codes,
    quote_identifier,
    require_indicator,
    rows_to_dicts,
)


def get_indicator_series(
    indicator_code: str,
    country_codes: list[str] | None = None,
    start_year: int | None = None,
    end_year: int | None = None,
) -> list[dict]:
    indicator = require_indicator(indicator_code)

    table_name = indicator.gold_table
    column_name = quote_identifier(indicator.code)

    countries = normalize_country_codes(country_codes)

    conditions = [f"{column_name} IS NOT NULL"]
    params: dict = {}

    if countries:
        conditions.append("country_code IN :country_codes")
        params["country_codes"] = countries

    if start_year is not None:
        conditions.append("year >= :start_year")
        params["start_year"] = start_year

    if end_year is not None:
        conditions.append("year <= :end_year")
        params["end_year"] = end_year

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
        ORDER BY country_code ASC, year ASC
        """
    )

    if countries:
        sql = sql.bindparams(bindparam("country_codes", expanding=True))

    with engine.connect() as conn:
        rows = conn.execute(sql, params).fetchall()

    return rows_to_dicts(rows)