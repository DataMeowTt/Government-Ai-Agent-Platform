from sqlalchemy import bindparam, text

from app.catalog.analytics_catalog import get_analytics_table_for_indicator
from app.db.postgres import get_postgres_engine
from app.tools.bigquery_tooling import (
    execute_bigquery_select,
    resolve_whitelisted_table,
    safe_identifier,
)
from app.tools.common import (
    normalize_country_codes,
    quote_identifier,
    require_family_support,
    require_indicator,
    rows_to_dicts,
    use_bigquery_data_source,
)


def get_indicator_analytics_series(
    indicator_code: str,
    country_codes: list[str] | None = None,
    start_year: int | None = None,
    end_year: int | None = None,
) -> list[dict]:
    canonical_indicator = require_family_support(indicator_code, "trend")
    indicator = require_indicator(indicator_code)

    analytics_table = get_analytics_table_for_indicator(canonical_indicator.code)

    if not analytics_table:
        return []

    if use_bigquery_data_source():
        analytics_table_name = resolve_whitelisted_table(analytics_table)
        gold_table_name = resolve_whitelisted_table(canonical_indicator.gold_table)
        countries = normalize_country_codes(country_codes)
        actual_col = safe_identifier(f"{canonical_indicator.code}_actual")
        trend_col = safe_identifier(f"{canonical_indicator.code}_trend")
        residual_col = safe_identifier(f"{canonical_indicator.code}_residual")
        anomaly_score_col = safe_identifier(f"{canonical_indicator.code}_anomaly_score")

        conditions = [f"a.{actual_col} IS NOT NULL"]
        params: dict = {
            "indicator_code": canonical_indicator.code,
            "unit": canonical_indicator.unit,
        }
        if countries:
            conditions.append("a.country_code IN UNNEST(@country_codes)")
            params["country_codes"] = countries
        if start_year is not None:
            conditions.append("a.year >= @start_year")
            params["start_year"] = start_year
        if end_year is not None:
            conditions.append("a.year <= @end_year")
            params["end_year"] = end_year

        where_sql = " AND ".join(conditions)
        sql = f"""
        SELECT
            a.country_code,
            g.country,
            a.year,
            @indicator_code AS indicator,
            a.{actual_col} AS actual_value,
            a.{trend_col} AS trend_value,
            a.{residual_col} AS residual_value,
            a.{anomaly_score_col} AS anomaly_score,
            @unit AS unit
        FROM `{analytics_table_name}` a
        LEFT JOIN `{gold_table_name}` g
          ON a.country_code = g.country_code
         AND a.year = g.year
        WHERE {where_sql}
        ORDER BY a.country_code ASC, a.year ASC
        """
        try:
            return execute_bigquery_select(
                sql=sql,
                referenced_tables=[analytics_table_name, gold_table_name],
                params=params,
            )
        except Exception:
            return []

    gold_table = indicator.gold_table
    actual_col = quote_identifier(f"{indicator_code}_actual")
    trend_col = quote_identifier(f"{indicator_code}_trend")
    residual_col = quote_identifier(f"{indicator_code}_residual")
    anomaly_score_col = quote_identifier(f"{indicator_code}_anomaly_score")
    countries = normalize_country_codes(country_codes)
    conditions = [f"a.{actual_col} IS NOT NULL"]
    params: dict = {}

    if countries:
        conditions.append("a.country_code IN :country_codes")
        params["country_codes"] = countries

    if start_year is not None:
        conditions.append("a.year >= :start_year")
        params["start_year"] = start_year

    if end_year is not None:
        conditions.append("a.year <= :end_year")
        params["end_year"] = end_year

    where_sql = " AND ".join(conditions)

    sql = text(
        f"""
        SELECT
            a.country_code,
            g.country,
            a.year,
            a.{actual_col} AS actual_value,
            a.{trend_col} AS trend_value,
            a.{residual_col} AS residual_value,
            a.{anomaly_score_col} AS anomaly_score
        FROM {analytics_table} a
        LEFT JOIN {gold_table} g
          ON a.country_code = g.country_code
         AND a.year = g.year
        WHERE {where_sql}
        ORDER BY a.country_code ASC, a.year ASC
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
