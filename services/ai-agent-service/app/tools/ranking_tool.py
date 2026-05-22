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


def rank_countries(
    indicator_code: str,
    year: int,
    limit: int = 10,
    order: str = "desc",
    country_codes: list[str] | None = None,
) -> list[dict]:
    canonical_indicator = require_family_support(indicator_code, "ranking")
    indicator = require_indicator(indicator_code)
    direction = "ASC" if str(order).lower() == "asc" else "DESC"
    safe_limit = max(1, min(int(limit or 10), 100))
    countries = normalize_country_codes(country_codes)

    if use_bigquery_data_source():
        table_name = resolve_whitelisted_table(canonical_indicator.gold_table)
        column_name = safe_identifier(canonical_indicator.gold_column)

        conditions = [
            "year = @year",
            f"{column_name} IS NOT NULL",
        ]
        params: dict = {
            "year": year,
            "limit": safe_limit,
            "indicator_code": canonical_indicator.code,
            "unit": canonical_indicator.unit,
        }

        if countries:
            conditions.append("country_code IN UNNEST(@country_codes)")
            params["country_codes"] = countries

        where_sql = " AND ".join(conditions)
        sql = f"""
        SELECT
            country_code,
            country,
            year,
            @indicator_code AS indicator,
            {column_name} AS value,
            @unit AS unit
        FROM `{table_name}`
        WHERE {where_sql}
        ORDER BY value {direction}
        LIMIT @limit
        """
        return execute_bigquery_select(
            sql=sql,
            referenced_tables=[table_name],
            params=params,
        )

    table_name = indicator.gold_table
    column_name = quote_identifier(indicator_column_name(indicator))

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

    with get_postgres_engine().connect() as conn:
        rows = conn.execute(sql, params).fetchall()

    output = rows_to_dicts(rows)
    for row in output:
        row["indicator"] = canonical_indicator.code
        row["unit"] = canonical_indicator.unit
    return output
