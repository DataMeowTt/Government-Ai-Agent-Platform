import pandas as pd
from functools import reduce
from sklearn.preprocessing import StandardScaler
from sklearn.impute import KNNImputer
from sklearn.cluster import KMeans
from sqlalchemy import inspect
from sqlalchemy import text

from src.core.database import get_engine
from src.core.logger import logger
from src.generated.indicator_contract import (
    INDICATORS_FOR_CLUSTER,
    PUBLIC_INDICATORS,
)

OPTIONAL_OUTPUT_COLUMNS = ("latest_valid_year", "run_id", "run_date", "loaded_at")


def _get_supported_metadata_columns(engine, table_name: str) -> list[str]:
    try:
        columns = {column["name"] for column in inspect(engine).get_columns(table_name)}
    except Exception as e:
        logger.warning(f"Could not inspect metadata columns for {table_name}: {e}")
        return []

    return [column for column in OPTIONAL_OUTPUT_COLUMNS if column in columns]

def find_table_for_indicator(indicator: str) -> str:
    indicator_meta = PUBLIC_INDICATORS.get(indicator)
    gold_table = indicator_meta.get("gold_table") if indicator_meta else None

    if not gold_table:
        raise ValueError(f"Table not found for indicator: {indicator}")

    return str(gold_table)

def get_clustering_data(target_year: int, lookback: int = 3) -> pd.DataFrame:
    engine = get_engine()
    queries = []
    for indicator in INDICATORS_FOR_CLUSTER:
        table = find_table_for_indicator(indicator)
        queries.append(f"""
            SELECT country_code, year, "{indicator}"
            FROM {table}
            WHERE year BETWEEN {target_year - lookback} AND {target_year}
        """)
        
    dfs = []
    for q in queries:
        try:
            dfs.append(pd.read_sql(text(q), engine))
        except Exception as e:
            logger.error(f"Failed to fetch data for query: {q} | Error: {e}")
            raise
            
    if not dfs:
        return pd.DataFrame()
        
    df_wide = reduce(lambda left, right: pd.merge(left, right, on=['country_code', 'year'], how='outer'), dfs)
    return df_wide

def forward_fill_by_country(df: pd.DataFrame, limit: int = 2) -> pd.DataFrame:
    df = df.sort_values(['country_code', 'year'])
    indicator_cols = [c for c in df.columns if c not in ['country_code', 'year']]
    df[indicator_cols] = df.groupby('country_code')[indicator_cols].ffill(limit=limit)
    return df

def prepare_cluster_matrix(target_year: int):
    df = get_clustering_data(target_year, lookback=3)
    if df.empty:
        return [], []
        
    df = forward_fill_by_country(df, limit=2)
    df_target = df[df['year'] == target_year].copy()
    
    threshold = 0.7 * len(INDICATORS_FOR_CLUSTER)
    df_target = df_target.dropna(thresh=threshold, subset=INDICATORS_FOR_CLUSTER)
    
    if df_target.empty:
        return [], []
        
    X = df_target[INDICATORS_FOR_CLUSTER].values
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    imputer = KNNImputer(n_neighbors=5)
    X_imputed = imputer.fit_transform(X_scaled)
    
    return df_target['country_code'].values, X_imputed

def run_clustering(
    target_year: int,
    n_clusters: int = 5,
    runtime_metadata: dict[str, str] | None = None,
    latest_valid_year: int | None = None,
):
    countries, X = prepare_cluster_matrix(target_year)
    
    if len(countries) < n_clusters:
        logger.warning(f"Not enough countries ({len(countries)}) for {n_clusters} clusters in year {target_year}.")
        return
        
    try:
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init='auto')
        clusters = kmeans.fit_predict(X)
        
        records = []
        for ctry, cluster in zip(countries, clusters):
            records.append({
                "year": target_year,
                "country_code": ctry,
                "cluster_id": int(cluster),
                "method": "kmeans",
            })
            
        records_df = pd.DataFrame(records)
        temp_table = f"temp_clusters_{target_year}"
        engine = get_engine()
        metadata_columns = _get_supported_metadata_columns(engine, "analytics_clusters")

        if runtime_metadata and metadata_columns:
            for column in metadata_columns:
                if column in runtime_metadata:
                    records_df[column] = runtime_metadata[column]

        if latest_valid_year is not None and "latest_valid_year" in metadata_columns:
            records_df["latest_valid_year"] = latest_valid_year

        insert_metadata_columns = "".join(
            f", {column}" for column in metadata_columns
        )
        select_metadata_columns = "".join(
            f", {column}" for column in metadata_columns
        )
        update_metadata_columns = "".join(
            f",\n                {column} = EXCLUDED.{column}" for column in metadata_columns
        )
        
        records_df.to_sql(temp_table, engine, if_exists="replace", index=False)
        
        update_sql = text(f"""
            INSERT INTO analytics_clusters (year, country_code, cluster_id, method{insert_metadata_columns})
            SELECT year, country_code, cluster_id, method{select_metadata_columns} FROM {temp_table}
            ON CONFLICT (year, country_code) DO UPDATE SET
                cluster_id = EXCLUDED.cluster_id,
                method = EXCLUDED.method{update_metadata_columns};
        """)
        
        drop_sql = text(f"DROP TABLE {temp_table}")
        
        with engine.begin() as conn:
            conn.execute(update_sql)
            conn.execute(drop_sql)
            
        logger.info(f"Successfully saved {len(records)} clusters for year {target_year}")
        
    except Exception as e:
        logger.error(f"Clustering failed for year {target_year}: {e}")
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {temp_table}"))
        raise
