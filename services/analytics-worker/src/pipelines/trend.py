import pandas as pd
from sklearn.linear_model import LinearRegression
from sqlalchemy import text
from src.core.database import engine
from src.core.logger import logger

def compute_trend_for_indicator(table_name: str, indicator: str):
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
        return []

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

def save_trends_to_analytics(table_name: str, indicator: str, results_df: pd.DataFrame):
    if results_df.empty:
        logger.info(f"No trend data to save for {indicator} in {table_name}")
        return
        
    temp_table = f"temp_{table_name}_{indicator}"
    
    try:
        results_df.to_sql(temp_table, engine, if_exists="replace", index=False)
        
        update_sql = text(f"""
            INSERT INTO analytics_{table_name} (
                country_code, year, 
                "{indicator}_actual", "{indicator}_trend", "{indicator}_residual",
                "{indicator}_slope", "{indicator}_intercept", "{indicator}_r2"
            )
            SELECT 
                country_code, year, 
                "{indicator}_actual", "{indicator}_trend", "{indicator}_residual",
                "{indicator}_slope", "{indicator}_intercept", "{indicator}_r2"
            FROM {temp_table}
            ON CONFLICT (country_code, year) DO UPDATE SET
                "{indicator}_actual" = EXCLUDED."{indicator}_actual",
                "{indicator}_trend" = EXCLUDED."{indicator}_trend",
                "{indicator}_residual" = EXCLUDED."{indicator}_residual",
                "{indicator}_slope" = EXCLUDED."{indicator}_slope",
                "{indicator}_intercept" = EXCLUDED."{indicator}_intercept",
                "{indicator}_r2" = EXCLUDED."{indicator}_r2";
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