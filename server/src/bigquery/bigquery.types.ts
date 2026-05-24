export type BackendDataSource = 'postgres' | 'bigquery';

export interface BigQueryAnomaliesParams {
  countryCode?: string;
  indicator?: string;
  threshold: number;
  limit: number;
  offset: number;
}

export interface BigQueryCountryItem {
  country_code: string;
  country_name: string;
  region: string | null;
}

export interface BigQueryClusterItem {
  country_code: string;
  country: string;
  year: number;
  cluster_id: number;
  latest_valid_year: number;
}

export interface BigQueryAnomalyItem {
  country_code: string;
  year: number;
  indicator: string;
  actual_value: number | null;
  anomaly_score: number | null;
  country_name: string;
}

export interface BigQueryCountryAnalyticsRow {
  country_code: string;
  year: number;
  actual_growth?: number | null;
  trend_growth?: number | null;
  anomaly_growth?: number | null;
  actual_debt?: number | null;
  anomaly_debt?: number | null;
  actual_inflation?: number | null;
  actual_poverty?: number | null;
  actual_unemployment?: number | null;
  actual_manuf_share?: number | null;
  actual_agri_share?: number | null;
  actual_reer_deviation?: number | null;
  anomaly_reer_deviation?: number | null;
  cluster_id?: number | null;
  completeness_score?: number | null;
  flag_score?: number | null;
}

export interface BigQueryCountryAnalyticsResponse {
  meta: {
    country_code: string;
    data_completeness: number;
    data_completeness_ratio?: number | null;
    data_completeness_percent?: number | null;
    flag_score: number;
    latest_year: number | null;
  };
  data: Array<{
    country_code: string;
    year: number;
    actual_growth?: number | null;
    trend_growth?: number | null;
    anomaly_growth?: number | null;
    actual_debt?: number | null;
    anomaly_debt?: number | null;
    actual_inflation?: number | null;
    actual_poverty?: number | null;
    actual_unemployment?: number | null;
    actual_manuf_share?: number | null;
    actual_agri_share?: number | null;
    actual_reer_deviation?: number | null;
    anomaly_reer_deviation?: number | null;
    cluster_id?: number | null;
  }>;
}

export interface BigQueryClusterBenchmarkMember {
  country_code: string;
  country_name: string;
  year: number;
  value: number | null;
}

export interface BigQueryClusterBenchmarkResponse {
  cluster_id: number;
  indicator: string;
  year: number;
  average: number;
  members: BigQueryClusterBenchmarkMember[];
}

export interface BigQueryCompareParams {
  countries: string[];
  indicator: string;
  from?: number;
  to?: number;
}

export interface BigQueryCompareRow {
  country_code: string;
  country: string;
  year: number;
  indicator: string;
  indicator_name: string;
  category: string;
  unit: string;
  value: number | null;
  trend_value?: number | null;
}

export interface BigQueryCountryIndicatorRow {
  country_code: string;
  country: string;
  year: number;
  indicator: string;
  indicator_name: string;
  category: string;
  unit: string;
  value: number | null;
  supports_trend: boolean;
  supports_anomaly: boolean;
  trend_value: number | null;
  residual_value: number | null;
  anomaly_score: number | null;
  is_anomaly: boolean;
  source_table: string;
}

export interface BigQueryCountryIndicatorSummary {
  indicator: string;
  latest_non_null_year: number | null;
  latest_non_null_value: number | null;
  coverage_ratio: number;
}

export interface BigQueryCountryIndicatorsResponse {
  country_code: string;
  rows: BigQueryCountryIndicatorRow[];
  summary: BigQueryCountryIndicatorSummary[];
}

export interface DataFreshnessSourceItem {
  name: string;
  version: string | null;
  updated_at: string | null;
}

export interface DataFreshnessResponse {
  available: boolean;
  last_successful_run_id: string | null;
  last_successful_sync_at: string | null;
  latest_data_year: number | null;
  sources: DataFreshnessSourceItem[];
  status: 'success' | 'unavailable';
}
