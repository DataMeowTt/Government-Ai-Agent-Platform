export interface Country {
  country_code: string;
  country_name: string;
  country?: string | null;
  region?: string | null;
}

export interface Indicator {
  code: string;
  name: string;
  name_vi?: string | null;
  name_en?: string | null;
  category: string;
  unit: string;
  table?: string | null;
  supports_compare?: boolean;
  supports_ranking?: boolean;
  supports_trend?: boolean;
  supports_anomaly?: boolean;
  supports_coverage?: boolean;
  description_vi?: string | null;
}

export interface AnomalyItem {
  country_code: string;
  country_name: string;
  year: number;
  indicator: string;
  actual_value: number | null;
  anomaly_score: number | null;
}

export interface ClusterItem {
  year: number;
  country_code: string;
  country?: string | null;
  cluster_id: number;
  latest_valid_year?: number;
}

export interface CountryAnalyticsMeta {
  country_code: string;
  data_completeness?: number | null;
  data_completeness_ratio?: number | null;
  data_completeness_percent?: number | null;
  flag_score?: number | null;
  latest_year?: number | null;
}

export interface CountryAnalyticsResponse {
  meta: CountryAnalyticsMeta;
  data: CountryAnalyticsRow[];
}

export interface ClusterBenchmarkMember {
  country_code: string;
  country_name?: string | null;
  year?: number | null;
  value: number | null;
}

export interface ClusterBenchmark {
  cluster_id: number;
  indicator: string;
  year: number;
  average: number;
  members: ClusterBenchmarkMember[];
}

export interface CountryAnalyticsRow {
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
}

export interface CompareDataPoint {
  year: number;
  value: number | null;
  trend_value?: number | null;
}

export interface CompareGroupedData {
  [countryCode: string]: CompareDataPoint[];
}

export interface CompareRow {
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

export interface CountryIndicatorRow {
  country_code: string;
  country: string;
  year: number;
  indicator: string;
  indicator_name: string;
  category: string;
  unit: string;
  value: number | null;
  supports_trend?: boolean;
  supports_anomaly?: boolean;
  trend_value?: number | null;
  residual_value?: number | null;
  anomaly_score?: number | null;
  is_anomaly?: boolean;
  source_table: string;
}

export interface CountryIndicatorSummary {
  indicator: string;
  latest_non_null_year: number | null;
  latest_non_null_value: number | null;
  coverage_ratio: number;
}

export interface CountryIndicatorsResponse {
  country_code: string;
  rows: CountryIndicatorRow[];
  summary: CountryIndicatorSummary[];
}

export interface DataFreshnessSource {
  name: string;
  version: string | null;
  updated_at: string | null;
}

export interface DataFreshnessResponse {
  available: boolean;
  last_successful_run_id: string | null;
  last_successful_sync_at: string | null;
  latest_data_year: number | null;
  sources: DataFreshnessSource[];
  status: 'success' | 'unavailable';
}
