import pandas as pd
from functools import reduce
from sklearn.preprocessing import StandardScaler
from sklearn.impute import KNNImputer
from sklearn.cluster import KMeans
from sqlalchemy import text
from src.core.database import engine
from src.core.logger import logger

INDICATORS_FOR_CLUSTER = [
    "agri_va_share", "manuf_va_share", "GFCF_to_GDP",
    "GNI_to_GDP", "poverty_headcount", "urban_pop_pct", "unemployment_total"
]

def find_table_for_indicator(indicator: str) -> str:
    mapping = {
        "gold_social_welfare": ["poverty_headcount", "urban_pop_pct", "unemployment_total"],
        "gold_structural_composition": ["agri_va_share", "manuf_va_share", "GFCF_to_GDP", "GNI_to_GDP"]
    }
    for table, indicators in mapping.items():
        if indicator in indicators:
            return table
    raise ValueError(f"Table not found for indicator: {indicator}")

def get_clustering_data(target_year: int, lookback: int = 3) -> pd.DataFrame:
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

def run_clustering(target_year: int, n_clusters: int = 5):
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
                "method": "kmeans"
            })
            
        records_df = pd.DataFrame(records)
        temp_table = f"temp_clusters_{target_year}"
        
        records_df.to_sql(temp_table, engine, if_exists="replace", index=False)
        
        update_sql = text(f"""
            INSERT INTO analytics_clusters (year, country_code, cluster_id, method)
            SELECT year, country_code, cluster_id, method FROM {temp_table}
            ON CONFLICT (year, country_code) DO UPDATE SET
                cluster_id = EXCLUDED.cluster_id,
                method = EXCLUDED.method;
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