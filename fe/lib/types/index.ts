export interface Country {
  country_code: string;
  country_name: string;
  region?: string | null;
}

export interface Indicator {
  code: string;
  name: string;
  category: string;
  unit: string;
  table: string;
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
  cluster_id: number;
  method: string;
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
}

export interface CompareGroupedData {
  [countryCode: string]: CompareDataPoint[];
}