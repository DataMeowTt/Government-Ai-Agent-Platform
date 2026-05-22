import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
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

def compute_anomaly_scores(residuals_series: pd.Series) -> np.ndarray:
    if len(residuals_series) < 5:
        return np.zeros(len(residuals_series))
        
    X = residuals_series.values.reshape(-1, 1)
    
    try:
        model = IsolationForest(contamination='auto', random_state=42)
        model.fit(X)
        scores = -model.decision_function(X)
        
        min_s = scores.min()
        max_s = scores.max()
        
        if max_s - min_s > 1e-6:
            scores = (scores - min_s) / (max_s - min_s)
        else:
            scores = np.zeros_like(scores)
    except Exception as e:
        logger.warning(f"Anomaly computation failed: {e}")
        scores = np.zeros(len(residuals_series))
        
    return scores

def update_anomaly_scores(
    table_name: str,
    indicator: str,
    runtime_metadata: dict[str, str] | None = None,
):
    engine = get_engine()
    analytics_table = f"analytics_{table_name}"
    query = f"""
        SELECT country_code, year, "{indicator}_residual"
        FROM {analytics_table}
        WHERE "{indicator}_residual" IS NOT NULL
    """
    
    try:
        df = pd.read_sql(query, engine)
    except Exception as e:
        logger.error(f"Failed to read residuals for {indicator} from {analytics_table}: {e}")
        raise

    if df.empty:
        return

    results = []
    
    for country, group in df.groupby("country_code"):
        scores = compute_anomaly_scores(group[f"{indicator}_residual"])
        
        for (_, row), score in zip(group.iterrows(), scores):
            results.append({
                "country_code": row["country_code"],
                "year": row["year"],
                f"{indicator}_anomaly_score": float(score)
            })
            
    if not results:
        return

    results_df = pd.DataFrame(results)
    temp_table = f"temp_anomaly_{table_name}_{indicator}".lower()
    metadata_columns = _get_supported_metadata_columns(engine, analytics_table)

    if runtime_metadata and metadata_columns:
        for column in metadata_columns:
            results_df[column] = runtime_metadata[column]

    metadata_updates = "".join(
        f",\n                {column} = t.{column}" for column in metadata_columns
    )
    
    try:
        results_df.to_sql(temp_table, engine, if_exists="replace", index=False)
        
        update_sql = text(f"""
            UPDATE {analytics_table}
            SET "{indicator}_anomaly_score" = t."{indicator}_anomaly_score"{metadata_updates}
            FROM {temp_table} t
            WHERE {analytics_table}.country_code = t.country_code
              AND {analytics_table}.year = t.year;
        """)
        
        drop_sql = text(f"DROP TABLE {temp_table}")
        
        with engine.begin() as conn:
            conn.execute(update_sql)
            conn.execute(drop_sql)
            
        logger.info(f"Successfully updated anomaly scores for {indicator} in {table_name}")
        
    except Exception as e:
        logger.error(f"Failed to save anomaly scores for {indicator} in {table_name}: {e}")
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {temp_table}"))
        raise
