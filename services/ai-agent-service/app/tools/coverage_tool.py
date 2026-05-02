from sqlalchemy import bindparam, text

from app.db.postgres import engine
from app.tools.common import (
    normalize_country_codes,
    quote_identifier,
    require_indicator,
    rows_to_dicts,
)


def get_data_coverage(
    indicator_code: str,
    country_codes: list[str] | None = None,
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

    where_sql = " AND ".join(conditions)

    sql = text(
        f"""
        SELECT
            country_code,
            MIN(country) AS country,
            MIN(year) AS min_year,
            MAX(year) AS max_year,
            COUNT(*) AS observations
        FROM {table_name}
        WHERE {where_sql}
        GROUP BY country_code
        ORDER BY country_code ASC
        """
    )

    if countries:
        sql = sql.bindparams(bindparam("country_codes", expanding=True))

    with engine.connect() as conn:
        rows = conn.execute(sql, params).fetchall()

    return rows_to_dicts(rows)