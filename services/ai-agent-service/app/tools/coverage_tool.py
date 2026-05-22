from sqlalchemy import bindparam, text

from app.db.postgres import get_postgres_engine
from app.tools.bigquery_tooling import (
    execute_bigquery_select,
    resolve_whitelisted_table,
    safe_identifier,
)
from app.tools.common import (
    indicator_column_name,
    normalize_country_codes,
    quote_identifier,
    require_family_support,
    require_indicator,
    rows_to_dicts,
    use_bigquery_data_source,
)


def get_data_coverage(
    indicator_code: str,
    country_codes: list[str] | None = None,
) -> list[dict]:
    canonical_indicator = require_family_support(indicator_code, "coverage")
    indicator = require_indicator(indicator_code)

    if use_bigquery_data_source():
        table_name = resolve_whitelisted_table(canonical_indicator.gold_table)
        column_name = safe_identifier(canonical_indicator.gold_column)
        countries = normalize_country_codes(country_codes)
        conditions = [f"{column_name} IS NOT NULL"]
        params: dict = {}

        if countries:
            conditions.append("country_code IN UNNEST(@country_codes)")
            params["country_codes"] = countries

        where_sql = " AND ".join(conditions)
        sql = f"""
        SELECT
            country_code,
            MIN(country) AS country,
            MIN(year) AS min_year,
            MAX(year) AS max_year,
            COUNT(*) AS observations
        FROM `{table_name}`
        WHERE {where_sql}
        GROUP BY country_code
        ORDER BY country_code ASC
        """
        return execute_bigquery_select(
            sql=sql,
            referenced_tables=[table_name],
            params=params,
        )

    table_name = indicator.gold_table
    column_name = quote_identifier(indicator_column_name(indicator))

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

    with get_postgres_engine().connect() as conn:
        rows = conn.execute(sql, params).fetchall()

    return rows_to_dicts(rows)
