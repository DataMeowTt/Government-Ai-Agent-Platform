-- Generated from contracts/*.yaml.
-- Do not edit manually.
-- Run: python scripts/generate_contract_artifacts.py

CREATE SCHEMA IF NOT EXISTS `gov_ai_silver`;
CREATE SCHEMA IF NOT EXISTS `gov_ai_gold`;
CREATE SCHEMA IF NOT EXISTS `gov_ai_analytics`;
CREATE SCHEMA IF NOT EXISTS `gov_ai_ops`;

CREATE TABLE IF NOT EXISTS `gov_ai_analytics.analytics_clusters` (
  `country_code` STRING NOT NULL,
  `country` STRING NOT NULL,
  `year` INTEGER NOT NULL,
  `cluster_id` INTEGER NOT NULL,
  `latest_valid_year` INTEGER NOT NULL,
  `run_id` STRING NOT NULL,
  `run_date` DATE NOT NULL,
  `loaded_at` TIMESTAMP NOT NULL
)
PARTITION BY RANGE_BUCKET(`year`, GENERATE_ARRAY(1980, 2030, 1))
CLUSTER BY `country_code`
;

CREATE TABLE IF NOT EXISTS `gov_ai_analytics.analytics_gold_crisis_risk` (
  `country_code` STRING NOT NULL,
  `country` STRING NOT NULL,
  `year` INTEGER NOT NULL,
  `REER_deviation_actual` FLOAT64,
  `REER_deviation_trend` FLOAT64,
  `REER_deviation_residual` FLOAT64,
  `REER_deviation_slope` FLOAT64,
  `REER_deviation_intercept` FLOAT64,
  `REER_deviation_r2` FLOAT64,
  `REER_deviation_anomaly_score` FLOAT64,
  `spending_efficiency_actual` FLOAT64,
  `spending_efficiency_trend` FLOAT64,
  `spending_efficiency_residual` FLOAT64,
  `spending_efficiency_slope` FLOAT64,
  `spending_efficiency_intercept` FLOAT64,
  `spending_efficiency_r2` FLOAT64,
  `spending_efficiency_anomaly_score` FLOAT64,
  `run_id` STRING NOT NULL,
  `run_date` DATE NOT NULL,
  `loaded_at` TIMESTAMP NOT NULL
)
PARTITION BY RANGE_BUCKET(`year`, GENERATE_ARRAY(1980, 2030, 1))
CLUSTER BY `country_code`
;

CREATE TABLE IF NOT EXISTS `gov_ai_analytics.analytics_gold_fiscal_monetary` (
  `country_code` STRING NOT NULL,
  `country` STRING NOT NULL,
  `year` INTEGER NOT NULL,
  `fiscal_balance_GDP_actual` FLOAT64,
  `fiscal_balance_GDP_trend` FLOAT64,
  `fiscal_balance_GDP_residual` FLOAT64,
  `fiscal_balance_GDP_slope` FLOAT64,
  `fiscal_balance_GDP_intercept` FLOAT64,
  `fiscal_balance_GDP_r2` FLOAT64,
  `fiscal_balance_GDP_anomaly_score` FLOAT64,
  `govdebt_GDP_actual` FLOAT64,
  `govdebt_GDP_trend` FLOAT64,
  `govdebt_GDP_residual` FLOAT64,
  `govdebt_GDP_slope` FLOAT64,
  `govdebt_GDP_intercept` FLOAT64,
  `govdebt_GDP_r2` FLOAT64,
  `govdebt_GDP_anomaly_score` FLOAT64,
  `inflation_cpi_actual` FLOAT64,
  `inflation_cpi_trend` FLOAT64,
  `inflation_cpi_residual` FLOAT64,
  `inflation_cpi_slope` FLOAT64,
  `inflation_cpi_intercept` FLOAT64,
  `inflation_cpi_r2` FLOAT64,
  `inflation_cpi_anomaly_score` FLOAT64,
  `inflation_gap_actual` FLOAT64,
  `inflation_gap_trend` FLOAT64,
  `inflation_gap_residual` FLOAT64,
  `inflation_gap_slope` FLOAT64,
  `inflation_gap_intercept` FLOAT64,
  `inflation_gap_r2` FLOAT64,
  `inflation_gap_anomaly_score` FLOAT64,
  `real_interest_rate_actual` FLOAT64,
  `real_interest_rate_trend` FLOAT64,
  `real_interest_rate_residual` FLOAT64,
  `real_interest_rate_slope` FLOAT64,
  `real_interest_rate_intercept` FLOAT64,
  `real_interest_rate_r2` FLOAT64,
  `real_interest_rate_anomaly_score` FLOAT64,
  `tax_revenue_pct_GDP_actual` FLOAT64,
  `tax_revenue_pct_GDP_trend` FLOAT64,
  `tax_revenue_pct_GDP_residual` FLOAT64,
  `tax_revenue_pct_GDP_slope` FLOAT64,
  `tax_revenue_pct_GDP_intercept` FLOAT64,
  `tax_revenue_pct_GDP_r2` FLOAT64,
  `tax_revenue_pct_GDP_anomaly_score` FLOAT64,
  `run_id` STRING NOT NULL,
  `run_date` DATE NOT NULL,
  `loaded_at` TIMESTAMP NOT NULL
)
PARTITION BY RANGE_BUCKET(`year`, GENERATE_ARRAY(1980, 2030, 1))
CLUSTER BY `country_code`
;

CREATE TABLE IF NOT EXISTS `gov_ai_analytics.analytics_gold_growth_dynamics` (
  `country_code` STRING NOT NULL,
  `country` STRING NOT NULL,
  `year` INTEGER NOT NULL,
  `GDP_growth_YoY_actual` FLOAT64,
  `GDP_growth_YoY_trend` FLOAT64,
  `GDP_growth_YoY_residual` FLOAT64,
  `GDP_growth_YoY_slope` FLOAT64,
  `GDP_growth_YoY_intercept` FLOAT64,
  `GDP_growth_YoY_r2` FLOAT64,
  `GDP_growth_YoY_anomaly_score` FLOAT64,
  `GDP_pc_growth_gap_actual` FLOAT64,
  `GDP_pc_growth_gap_trend` FLOAT64,
  `GDP_pc_growth_gap_residual` FLOAT64,
  `GDP_pc_growth_gap_slope` FLOAT64,
  `GDP_pc_growth_gap_intercept` FLOAT64,
  `GDP_pc_growth_gap_r2` FLOAT64,
  `GDP_pc_growth_gap_anomaly_score` FLOAT64,
  `rGDP_growth_YoY_actual` FLOAT64,
  `rGDP_growth_YoY_trend` FLOAT64,
  `rGDP_growth_YoY_residual` FLOAT64,
  `rGDP_growth_YoY_slope` FLOAT64,
  `rGDP_growth_YoY_intercept` FLOAT64,
  `rGDP_growth_YoY_r2` FLOAT64,
  `rGDP_growth_YoY_anomaly_score` FLOAT64,
  `rolling_mean_5yr_actual` FLOAT64,
  `rolling_mean_5yr_trend` FLOAT64,
  `rolling_mean_5yr_residual` FLOAT64,
  `rolling_mean_5yr_slope` FLOAT64,
  `rolling_mean_5yr_intercept` FLOAT64,
  `rolling_mean_5yr_r2` FLOAT64,
  `rolling_mean_5yr_anomaly_score` FLOAT64,
  `trend_deviation_actual` FLOAT64,
  `trend_deviation_trend` FLOAT64,
  `trend_deviation_residual` FLOAT64,
  `trend_deviation_slope` FLOAT64,
  `trend_deviation_intercept` FLOAT64,
  `trend_deviation_r2` FLOAT64,
  `trend_deviation_anomaly_score` FLOAT64,
  `run_id` STRING NOT NULL,
  `run_date` DATE NOT NULL,
  `loaded_at` TIMESTAMP NOT NULL
)
PARTITION BY RANGE_BUCKET(`year`, GENERATE_ARRAY(1980, 2030, 1))
CLUSTER BY `country_code`
;

CREATE TABLE IF NOT EXISTS `gov_ai_analytics.analytics_gold_social_welfare` (
  `country_code` STRING NOT NULL,
  `country` STRING NOT NULL,
  `year` INTEGER NOT NULL,
  `hcons_growth_actual` FLOAT64,
  `hcons_growth_trend` FLOAT64,
  `hcons_growth_residual` FLOAT64,
  `hcons_growth_slope` FLOAT64,
  `hcons_growth_intercept` FLOAT64,
  `hcons_growth_r2` FLOAT64,
  `hcons_growth_anomaly_score` FLOAT64,
  `poverty_change_5yr_actual` FLOAT64,
  `poverty_change_5yr_trend` FLOAT64,
  `poverty_change_5yr_residual` FLOAT64,
  `poverty_change_5yr_slope` FLOAT64,
  `poverty_change_5yr_intercept` FLOAT64,
  `poverty_change_5yr_r2` FLOAT64,
  `poverty_change_5yr_anomaly_score` FLOAT64,
  `poverty_headcount_actual` FLOAT64,
  `poverty_headcount_trend` FLOAT64,
  `poverty_headcount_residual` FLOAT64,
  `poverty_headcount_slope` FLOAT64,
  `poverty_headcount_intercept` FLOAT64,
  `poverty_headcount_r2` FLOAT64,
  `poverty_headcount_anomaly_score` FLOAT64,
  `unemployment_total_actual` FLOAT64,
  `unemployment_total_trend` FLOAT64,
  `unemployment_total_residual` FLOAT64,
  `unemployment_total_slope` FLOAT64,
  `unemployment_total_intercept` FLOAT64,
  `unemployment_total_r2` FLOAT64,
  `unemployment_total_anomaly_score` FLOAT64,
  `youth_unemployment_gap_actual` FLOAT64,
  `youth_unemployment_gap_trend` FLOAT64,
  `youth_unemployment_gap_residual` FLOAT64,
  `youth_unemployment_gap_slope` FLOAT64,
  `youth_unemployment_gap_intercept` FLOAT64,
  `youth_unemployment_gap_r2` FLOAT64,
  `youth_unemployment_gap_anomaly_score` FLOAT64,
  `run_id` STRING NOT NULL,
  `run_date` DATE NOT NULL,
  `loaded_at` TIMESTAMP NOT NULL
)
PARTITION BY RANGE_BUCKET(`year`, GENERATE_ARRAY(1980, 2030, 1))
CLUSTER BY `country_code`
;

CREATE TABLE IF NOT EXISTS `gov_ai_analytics.analytics_gold_structural_composition` (
  `country_code` STRING NOT NULL,
  `country` STRING NOT NULL,
  `year` INTEGER NOT NULL,
  `GFCF_to_GDP_actual` FLOAT64,
  `GFCF_to_GDP_trend` FLOAT64,
  `GFCF_to_GDP_residual` FLOAT64,
  `GFCF_to_GDP_slope` FLOAT64,
  `GFCF_to_GDP_intercept` FLOAT64,
  `GFCF_to_GDP_r2` FLOAT64,
  `GFCF_to_GDP_anomaly_score` FLOAT64,
  `GNI_to_GDP_actual` FLOAT64,
  `GNI_to_GDP_trend` FLOAT64,
  `GNI_to_GDP_residual` FLOAT64,
  `GNI_to_GDP_slope` FLOAT64,
  `GNI_to_GDP_intercept` FLOAT64,
  `GNI_to_GDP_r2` FLOAT64,
  `GNI_to_GDP_anomaly_score` FLOAT64,
  `agri_va_share_actual` FLOAT64,
  `agri_va_share_trend` FLOAT64,
  `agri_va_share_residual` FLOAT64,
  `agri_va_share_slope` FLOAT64,
  `agri_va_share_intercept` FLOAT64,
  `agri_va_share_r2` FLOAT64,
  `agri_va_share_anomaly_score` FLOAT64,
  `food_bev_share_manuf_actual` FLOAT64,
  `food_bev_share_manuf_trend` FLOAT64,
  `food_bev_share_manuf_residual` FLOAT64,
  `food_bev_share_manuf_slope` FLOAT64,
  `food_bev_share_manuf_intercept` FLOAT64,
  `food_bev_share_manuf_r2` FLOAT64,
  `food_bev_share_manuf_anomaly_score` FLOAT64,
  `manuf_va_share_actual` FLOAT64,
  `manuf_va_share_trend` FLOAT64,
  `manuf_va_share_residual` FLOAT64,
  `manuf_va_share_slope` FLOAT64,
  `manuf_va_share_intercept` FLOAT64,
  `manuf_va_share_r2` FLOAT64,
  `manuf_va_share_anomaly_score` FLOAT64,
  `run_id` STRING NOT NULL,
  `run_date` DATE NOT NULL,
  `loaded_at` TIMESTAMP NOT NULL
)
PARTITION BY RANGE_BUCKET(`year`, GENERATE_ARRAY(1980, 2030, 1))
CLUSTER BY `country_code`
;

CREATE TABLE IF NOT EXISTS `gov_ai_ops.data_quality_results` (
  `run_id` STRING NOT NULL,
  `run_date` DATE NOT NULL,
  `check_name` STRING NOT NULL,
  `severity` STRING NOT NULL,
  `status` STRING NOT NULL,
  `message` STRING,
  `details` JSON,
  `created_at` TIMESTAMP NOT NULL
)
PARTITION BY `run_date`
CLUSTER BY `status`
;

CREATE TABLE IF NOT EXISTS `gov_ai_gold.gold_crisis_risk` (
  `country_code` STRING NOT NULL,
  `country` STRING NOT NULL,
  `year` INTEGER NOT NULL,
  `income_group` STRING,
  `development_group` STRING,
  `rGDP_growth_YoY` FLOAT64,
  `govdebt_GDP` FLOAT64,
  `fiscal_balance_GDP` FLOAT64,
  `SovDebtCrisis` INTEGER,
  `CurrencyCrisis` INTEGER,
  `BankingCrisis` INTEGER,
  `crisis_composite` INTEGER,
  `crisis_any` INTEGER,
  `REER_deviation` FLOAT64,
  `spending_efficiency` FLOAT64,
  `completeness_score` FLOAT64,
  `run_id` STRING NOT NULL,
  `run_date` DATE NOT NULL,
  `loaded_at` TIMESTAMP NOT NULL
)
PARTITION BY RANGE_BUCKET(`year`, GENERATE_ARRAY(1980, 2030, 1))
CLUSTER BY `country_code`
;

CREATE TABLE IF NOT EXISTS `gov_ai_gold.gold_fiscal_monetary` (
  `country_code` STRING NOT NULL,
  `country` STRING NOT NULL,
  `year` INTEGER NOT NULL,
  `income_group` STRING,
  `development_group` STRING,
  `govdebt_GDP` FLOAT64,
  `debt_change_YoY` FLOAT64,
  `govrev_GDP` FLOAT64,
  `govexp_GDP` FLOAT64,
  `fiscal_balance_GDP` FLOAT64,
  `cumulative_deficit_5yr` FLOAT64,
  `ltrate` FLOAT64,
  `infl` FLOAT64,
  `real_interest_rate` FLOAT64,
  `tax_revenue_pct_GDP` FLOAT64,
  `inflation_cpi` FLOAT64,
  `inflation_deflator` FLOAT64,
  `inflation_gap` FLOAT64,
  `rolling_3yr_avg_cpi` FLOAT64,
  `completeness_score` FLOAT64,
  `run_id` STRING NOT NULL,
  `run_date` DATE NOT NULL,
  `loaded_at` TIMESTAMP NOT NULL
)
PARTITION BY RANGE_BUCKET(`year`, GENERATE_ARRAY(1980, 2030, 1))
CLUSTER BY `country_code`
;

CREATE TABLE IF NOT EXISTS `gov_ai_gold.gold_growth_dynamics` (
  `country_code` STRING NOT NULL,
  `country` STRING NOT NULL,
  `year` INTEGER NOT NULL,
  `income_group` STRING,
  `development_group` STRING,
  `rGDP_growth_YoY` FLOAT64,
  `rolling_mean_5yr` FLOAT64,
  `GDP_growth_YoY` FLOAT64,
  `GDP_growth_trend_5yr` FLOAT64,
  `trend_deviation` FLOAT64,
  `GDP_pc_growth_gap` FLOAT64,
  `log_rGDP_pc_USD` FLOAT64,
  `completeness_score` FLOAT64,
  `run_id` STRING NOT NULL,
  `run_date` DATE NOT NULL,
  `loaded_at` TIMESTAMP NOT NULL
)
PARTITION BY RANGE_BUCKET(`year`, GENERATE_ARRAY(1980, 2030, 1))
CLUSTER BY `country_code`
;

CREATE TABLE IF NOT EXISTS `gov_ai_gold.gold_social_welfare` (
  `country_code` STRING NOT NULL,
  `country` STRING NOT NULL,
  `year` INTEGER NOT NULL,
  `income_group` STRING,
  `development_group` STRING,
  `unemployment_total` FLOAT64,
  `unemployment_youth` FLOAT64,
  `youth_unemployment_gap` FLOAT64,
  `youth_gap_ratio` FLOAT64,
  `self_employed_pct` FLOAT64,
  `poverty_headcount` FLOAT64,
  `poverty_change_5yr` FLOAT64,
  `urban_pop_pct` FLOAT64,
  `urban_pop_growth` FLOAT64,
  `pop_density` FLOAT64,
  `log_pop_density` FLOAT64,
  `pop_growth` FLOAT64,
  `hcons_share` FLOAT64,
  `hcons_growth` FLOAT64,
  `trade_pct_gdp` FLOAT64,
  `completeness_score` FLOAT64,
  `run_id` STRING NOT NULL,
  `run_date` DATE NOT NULL,
  `loaded_at` TIMESTAMP NOT NULL
)
PARTITION BY RANGE_BUCKET(`year`, GENERATE_ARRAY(1980, 2030, 1))
CLUSTER BY `country_code`
;

CREATE TABLE IF NOT EXISTS `gov_ai_gold.gold_structural_composition` (
  `country_code` STRING NOT NULL,
  `country` STRING NOT NULL,
  `year` INTEGER NOT NULL,
  `income_group` STRING,
  `development_group` STRING,
  `GDP_growth_YoY` FLOAT64,
  `GDP_value` FLOAT64,
  `GFCF_value` FLOAT64,
  `GNI_value` FLOAT64,
  `Agri_VA` FLOAT64,
  `Manuf_VA` FLOAT64,
  `VA_FoodBev` FLOAT64,
  `GFCF_to_GDP` FLOAT64,
  `GNI_to_GDP` FLOAT64,
  `agri_va_share` FLOAT64,
  `manuf_va_share` FLOAT64,
  `food_bev_share_manuf` FLOAT64,
  `decade` FLOAT64,
  `flag_score` FLOAT64,
  `completeness_score` FLOAT64,
  `run_id` STRING NOT NULL,
  `run_date` DATE NOT NULL,
  `loaded_at` TIMESTAMP NOT NULL
)
PARTITION BY RANGE_BUCKET(`year`, GENERATE_ARRAY(1980, 2030, 1))
CLUSTER BY `country_code`
;

CREATE TABLE IF NOT EXISTS `gov_ai_ops.indicator_contract_versions` (
  `contract_version` STRING NOT NULL,
  `published_date` DATE NOT NULL,
  `sha256` STRING,
  `source_uri` STRING,
  `created_at` TIMESTAMP NOT NULL
)
;

CREATE TABLE IF NOT EXISTS `gov_ai_ops.job_logs` (
  `run_id` STRING NOT NULL,
  `run_date` DATE NOT NULL,
  `job_name` STRING NOT NULL,
  `status` STRING NOT NULL,
  `started_at` TIMESTAMP NOT NULL,
  `finished_at` TIMESTAMP,
  `duration_seconds` FLOAT64,
  `error_message` STRING
)
PARTITION BY `run_date`
CLUSTER BY `status`
;

CREATE TABLE IF NOT EXISTS `gov_ai_ops.pipeline_runs` (
  `run_id` STRING NOT NULL,
  `run_date` DATE NOT NULL,
  `status` STRING NOT NULL,
  `source_changed` BOOL,
  `raw_hashes` JSON,
  `silver_rows` INTEGER,
  `gold_rows` JSON,
  `analytics_rows` JSON,
  `started_at` TIMESTAMP NOT NULL,
  `finished_at` TIMESTAMP,
  `error_message` STRING
)
PARTITION BY `run_date`
CLUSTER BY `status`
;

CREATE TABLE IF NOT EXISTS `gov_ai_silver.silver_indicators` (
  `country_code` STRING NOT NULL,
  `country` STRING NOT NULL,
  `year` INTEGER NOT NULL,
  `indicator` STRING NOT NULL,
  `value` FLOAT64,
  `source` STRING NOT NULL,
  `run_id` STRING NOT NULL,
  `run_date` DATE NOT NULL,
  `loaded_at` TIMESTAMP NOT NULL
)
PARTITION BY RANGE_BUCKET(`year`, GENERATE_ARRAY(1980, 2030, 1))
CLUSTER BY `country_code`, `indicator`, `source`
;

CREATE TABLE IF NOT EXISTS `gov_ai_ops.source_snapshots` (
  `run_id` STRING NOT NULL,
  `run_date` DATE NOT NULL,
  `source_name` STRING NOT NULL,
  `source_uri` STRING,
  `snapshot_uri` STRING,
  `sha256` STRING,
  `bytes` INTEGER,
  `status` STRING NOT NULL,
  `created_at` TIMESTAMP NOT NULL,
  `error_message` STRING
)
PARTITION BY `run_date`
CLUSTER BY `status`
;
