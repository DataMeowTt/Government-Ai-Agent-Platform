import pandas as pd
from sklearn.linear_model import LinearRegression
from sqlalchemy import inspect
from sqlalchemy import text
from src.core.database import get_engine
from src.core.logger import logger

METADATA_COLUMNS = ("run_id", "run_date", "loaded_at")


def _get_supported_metadata_columns(engine, table_name: str) -> list[str]:
    try:
        columns = {column["name"] for column in inspect(engine).get_columns(table_name)}
    except Exception as e:
        logger.warning(f"Could not inspect metadata columns for {table_name}: {e}")
        return []

    return [column for column in METADATA_COLUMNS if column in columns]

def compute_trend_for_indicator(table_name: str, indicator: str):
    engine = get_engine()
    query = f"""
        SELECT country_code, year, "{indicator}"
        FROM {table_name}
        WHERE "{indicator}" IS NOT NULL
        ORDER BY country_code, year
    """
    
    try:
        df = pd.read_sql(query, engine)
    except Exception as e:
        logger.error(f"Failed to read data for {indicator} from {table_name}: {e}")
        raise

    results = []
    
    for country, group in df.groupby("country_code"):
        group = group.sort_values("year")
        if len(group) < 3:
            continue
            
        X = group[["year"]].values
        y = group[indicator].values
        
        try:
            model = LinearRegression().fit(X, y)
            slope = model.coef_[0]
            intercept = model.intercept_
            r2 = model.score(X, y)
            trend_vals = model.predict(X)
            
            for year, actual, trend in zip(group["year"], y, trend_vals):
                residual = actual - trend
                results.append({
                    "country_code": country,
                    "year": year,
                    f"{indicator}_actual": actual,
                    f"{indicator}_trend": trend,
                    f"{indicator}_residual": residual,
                    f"{indicator}_slope": slope,
                    f"{indicator}_intercept": intercept,
                    f"{indicator}_r2": r2
                })
        except Exception as e:
            logger.warning(f"Trend computation failed for {country} - {indicator}: {e}")
            continue
            
    return results

def save_trends_to_analytics(
    table_name: str,
    indicator: str,
    results_df: pd.DataFrame,
    runtime_metadata: dict[str, str] | None = None,
):
    if results_df.empty:
        logger.info(f"No trend data to save for {indicator} in {table_name}")
        return
        
    temp_table = f"temp_{table_name}_{indicator}".lower()
    analytics_table = f"analytics_{table_name}"
    engine = get_engine()
    metadata_columns = _get_supported_metadata_columns(engine, analytics_table)

    if runtime_metadata and metadata_columns:
        for column in metadata_columns:
            results_df[column] = runtime_metadata[column]

    insert_metadata_columns = "".join(
        f", {column}" for column in metadata_columns
    )
    select_metadata_columns = "".join(
        f", {column}" for column in metadata_columns
    )
    update_metadata_columns = "".join(
        f',\n                {column} = EXCLUDED.{column}' for column in metadata_columns
    )
    
    try:
        results_df.to_sql(temp_table, engine, if_exists="replace", index=False)
        
        update_sql = text(f"""
            INSERT INTO {analytics_table} (
                country_code, year, 
                "{indicator}_actual", "{indicator}_trend", "{indicator}_residual",
                "{indicator}_slope", "{indicator}_intercept", "{indicator}_r2"{insert_metadata_columns}
            )
            SELECT 
                country_code, year, 
                "{indicator}_actual", "{indicator}_trend", "{indicator}_residual",
                "{indicator}_slope", "{indicator}_intercept", "{indicator}_r2"{select_metadata_columns}
            FROM {temp_table}
            ON CONFLICT (country_code, year) DO UPDATE SET
                "{indicator}_actual" = EXCLUDED."{indicator}_actual",
                "{indicator}_trend" = EXCLUDED."{indicator}_trend",
                "{indicator}_residual" = EXCLUDED."{indicator}_residual",
                "{indicator}_slope" = EXCLUDED."{indicator}_slope",
                "{indicator}_intercept" = EXCLUDED."{indicator}_intercept",
                "{indicator}_r2" = EXCLUDED."{indicator}_r2"{update_metadata_columns};
        """)
        
        drop_sql = text(f"DROP TABLE {temp_table}")
        
        with engine.begin() as conn:
            conn.execute(update_sql)
            conn.execute(drop_sql)
            
        logger.info(f"Successfully saved trends for {indicator} in {table_name}")
        
    except Exception as e:
        logger.error(f"Failed to save trends for {indicator} in {table_name}: {e}")
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {temp_table}"))
        raise
