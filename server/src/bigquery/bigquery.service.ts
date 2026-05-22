import { BadRequestException, Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { BigQuery } from '@google-cloud/bigquery';
import { BigQueryCacheService } from './bigquery-cache.service';
import {
  BigQueryAnomaliesParams,
  BigQueryAnomalyItem,
  BigQueryClusterItem,
  BigQueryClusterBenchmarkResponse,
  BigQueryCompareParams,
  BigQueryCompareRow,
  BigQueryCountryAnalyticsResponse,
  BigQueryCountryAnalyticsRow,
  BigQueryCountryIndicatorRow,
  BigQueryCountryIndicatorsResponse,
  BigQueryCountryItem,
} from './bigquery.types';
import {
  GeneratedIndicatorContract,
  getIndicator,
  listIndicators,
} from '../generated/indicator-contract';

const DEFAULT_PROJECT_ID = 'western-pivot-452008-a6';
const DEFAULT_LOCATION = 'asia-southeast1';
const DEFAULT_GOLD_DATASET = 'gov_ai_gold';
const DEFAULT_ANALYTICS_DATASET = 'gov_ai_analytics';
const DEFAULT_MAX_BYTES_BILLED = 100000000;
const DEFAULT_CACHE_TTL_SECONDS = 300;
const MAX_LIMIT = 100;
type BigQueryTables = {
  goldGrowthDynamics: string;
  goldFiscalMonetary: string;
  goldSocialWelfare: string;
  goldCrisisRisk: string;
  goldStructuralComposition: string;
  analyticsClusters: string;
  analyticsGoldGrowthDynamics: string;
  analyticsGoldFiscalMonetary: string;
  analyticsGoldSocialWelfare: string;
  analyticsGoldStructuralComposition: string;
  analyticsGoldCrisisRisk: string;
};

const SAFE_IDENTIFIER_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*$/;
const ANOMALY_ALIAS_MAP: Record<string, string> = {
  growth: 'rGDP_growth_YoY',
  rgdp_growth_yoy: 'rGDP_growth_YoY',
  govdebt: 'govdebt_GDP',
  govdebt_gdp: 'govdebt_GDP',
  reer: 'REER_deviation',
  reer_deviation: 'REER_deviation',
};

@Injectable()
export class BigQueryService {
  private readonly projectId: string;
  private readonly location: string;
  private readonly goldDataset: string;
  private readonly analyticsDataset: string;
  private readonly maximumBytesBilled: number;
  private readonly cacheTtlSeconds: number;
  private readonly client: BigQuery;
  private readonly tables: BigQueryTables;
  private readonly whitelistedTables: Set<string>;
  private readonly indicators = listIndicators();
  private readonly indicatorsByCode = new Map<string, GeneratedIndicatorContract>(
    this.indicators.map(indicator => [indicator.code, indicator]),
  );
  private readonly anomalyIndicatorsByCode = new Map<
    string,
    GeneratedIndicatorContract
  >(
    this.indicators
      .filter(
        indicator =>
          indicator.supports_anomaly &&
          indicator.analytics_table &&
          indicator.gold_column,
      )
      .map(indicator => [indicator.code, indicator]),
  );

  constructor(
    private readonly configService: ConfigService,
    private readonly cacheService: BigQueryCacheService,
  ) {
    this.projectId =
      this.configService.get<string>('BIGQUERY_PROJECT_ID') || DEFAULT_PROJECT_ID;
    this.location =
      this.configService.get<string>('BIGQUERY_LOCATION') || DEFAULT_LOCATION;
    this.goldDataset =
      this.configService.get<string>('BIGQUERY_GOLD_DATASET') ||
      DEFAULT_GOLD_DATASET;
    this.analyticsDataset =
      this.configService.get<string>('BIGQUERY_ANALYTICS_DATASET') ||
      DEFAULT_ANALYTICS_DATASET;
    this.maximumBytesBilled = Number(
      this.configService.get<string>('BIGQUERY_MAX_BYTES_BILLED') ||
        DEFAULT_MAX_BYTES_BILLED,
    );
    this.cacheTtlSeconds = Number(
      this.configService.get<string>('BIGQUERY_CACHE_TTL_SECONDS') ||
        DEFAULT_CACHE_TTL_SECONDS,
    );

    this.tables = {
      goldGrowthDynamics: this.buildTableRef(
        this.goldDataset,
        'gold_growth_dynamics',
      ),
      goldFiscalMonetary: this.buildTableRef(
        this.goldDataset,
        'gold_fiscal_monetary',
      ),
      goldSocialWelfare: this.buildTableRef(
        this.goldDataset,
        'gold_social_welfare',
      ),
      goldCrisisRisk: this.buildTableRef(this.goldDataset, 'gold_crisis_risk'),
      goldStructuralComposition: this.buildTableRef(
        this.goldDataset,
        'gold_structural_composition',
      ),
      analyticsClusters: this.buildTableRef(
        this.analyticsDataset,
        'analytics_clusters',
      ),
      analyticsGoldGrowthDynamics: this.buildTableRef(
        this.analyticsDataset,
        'analytics_gold_growth_dynamics',
      ),
      analyticsGoldFiscalMonetary: this.buildTableRef(
        this.analyticsDataset,
        'analytics_gold_fiscal_monetary',
      ),
      analyticsGoldSocialWelfare: this.buildTableRef(
        this.analyticsDataset,
        'analytics_gold_social_welfare',
      ),
      analyticsGoldStructuralComposition: this.buildTableRef(
        this.analyticsDataset,
        'analytics_gold_structural_composition',
      ),
      analyticsGoldCrisisRisk: this.buildTableRef(
        this.analyticsDataset,
        'analytics_gold_crisis_risk',
      ),
    };

    this.whitelistedTables = new Set<string>([
      this.tables.goldGrowthDynamics,
      this.tables.goldFiscalMonetary,
      this.tables.goldSocialWelfare,
      this.tables.goldCrisisRisk,
      this.tables.goldStructuralComposition,
      this.tables.analyticsClusters,
      this.tables.analyticsGoldGrowthDynamics,
      this.tables.analyticsGoldFiscalMonetary,
      this.tables.analyticsGoldSocialWelfare,
      this.tables.analyticsGoldStructuralComposition,
      this.tables.analyticsGoldCrisisRisk,
    ]);

    this.indicators.forEach(indicator => {
      if (indicator.gold_table) {
        this.whitelistedTables.add(
          this.buildTableRef(this.goldDataset, indicator.gold_table),
        );
      }
      if (indicator.analytics_table) {
        this.whitelistedTables.add(
          this.buildTableRef(this.analyticsDataset, indicator.analytics_table),
        );
      }
    });

    this.client = new BigQuery({ projectId: this.projectId });
  }

  async listCountries(): Promise<BigQueryCountryItem[]> {
    const sql = `
      WITH ranked AS (
        SELECT
          g.country_code AS country_code,
          g.country AS country_name,
          g.income_group AS region,
          ROW_NUMBER() OVER (
            PARTITION BY g.country_code
            ORDER BY g.country ASC
          ) AS rn
        FROM \`${this.tables.goldGrowthDynamics}\` g
      )
      SELECT
        country_code,
        country_name,
        region
      FROM ranked
      WHERE rn = 1
      ORDER BY country_name ASC, country_code ASC
      LIMIT @limit
    `;
    return this.executeQuery<BigQueryCountryItem>(sql, { limit: MAX_LIMIT });
  }

  async getFullCountryAnalytics(
    countryCode: string,
  ): Promise<BigQueryCountryAnalyticsResponse> {
    const normalizedCountryCode = this.normalizeCountryCode(countryCode) || countryCode;
    const sql = `
      SELECT
        g.country_code AS country_code,
        g.year AS year,
        g.rGDP_growth_YoY AS actual_growth,
        an_growth.rGDP_growth_YoY_trend AS trend_growth,
        an_growth.rGDP_growth_YoY_anomaly_score AS anomaly_growth,
        an_fiscal.govdebt_GDP_actual AS actual_debt,
        an_fiscal.govdebt_GDP_anomaly_score AS anomaly_debt,
        an_fiscal.inflation_cpi_actual AS actual_inflation,
        an_social.poverty_headcount_actual AS actual_poverty,
        an_social.unemployment_total_actual AS actual_unemployment,
        an_struct.manuf_va_share_actual AS actual_manuf_share,
        an_struct.agri_va_share_actual AS actual_agri_share,
        an_risk.REER_deviation_actual AS actual_reer_deviation,
        an_risk.REER_deviation_anomaly_score AS anomaly_reer_deviation,
        c.cluster_id AS cluster_id,
        g.completeness_score AS completeness_score,
        COALESCE(gold_struct.flag_score, 0) AS flag_score
      FROM \`${this.tables.goldGrowthDynamics}\` g
      LEFT JOIN \`${this.tables.analyticsGoldGrowthDynamics}\` an_growth
        ON g.country_code = an_growth.country_code AND g.year = an_growth.year
      LEFT JOIN \`${this.tables.analyticsGoldFiscalMonetary}\` an_fiscal
        ON g.country_code = an_fiscal.country_code AND g.year = an_fiscal.year
      LEFT JOIN \`${this.tables.analyticsGoldSocialWelfare}\` an_social
        ON g.country_code = an_social.country_code AND g.year = an_social.year
      LEFT JOIN \`${this.tables.analyticsGoldStructuralComposition}\` an_struct
        ON g.country_code = an_struct.country_code AND g.year = an_struct.year
      LEFT JOIN \`${this.tables.goldStructuralComposition}\` gold_struct
        ON g.country_code = gold_struct.country_code AND g.year = gold_struct.year
      LEFT JOIN \`${this.tables.analyticsGoldCrisisRisk}\` an_risk
        ON g.country_code = an_risk.country_code AND g.year = an_risk.year
      LEFT JOIN \`${this.tables.analyticsClusters}\` c
        ON g.country_code = c.country_code AND g.year = c.year
      WHERE g.country_code = @countryCode
      ORDER BY g.year ASC
      LIMIT @limit
    `;

    const rows = await this.executeQuery<BigQueryCountryAnalyticsRow>(sql, {
      countryCode: normalizedCountryCode,
      limit: MAX_LIMIT,
    });

    const latestRow = rows.length > 0 ? rows[rows.length - 1] : undefined;
    const completenessRatio =
      rows.length > 0
        ? rows.reduce((sum, row) => {
            const normalized = this.normalizeCompletenessRatio(
              row.completeness_score,
            );
            return sum + (normalized ?? 0);
          }, 0) / rows.length
        : null;
    const completenessPercent =
      completenessRatio == null
        ? null
        : Number((completenessRatio * 100).toFixed(2));
    const responseRows = rows.map(({ completeness_score, flag_score, ...row }) => row);

    return {
      meta: {
        country_code: normalizedCountryCode,
        data_completeness_ratio:
          completenessRatio == null ? null : Number(completenessRatio.toFixed(4)),
        data_completeness_percent: completenessPercent,
        data_completeness: completenessPercent ?? 0,
        flag_score: Number(latestRow?.flag_score || 0),
        latest_year: latestRow ? Number(latestRow.year) : null,
      },
      data: responseRows,
    };
  }

  async getCompareRows(params: BigQueryCompareParams): Promise<BigQueryCompareRow[]> {
    const indicator = this.getComparableIndicatorOrThrow(params.indicator);
    const countries = Array.from(
      new Set(
        (params.countries || [])
          .map(code => this.normalizeCountryCode(code))
          .filter((code): code is string => Boolean(code)),
      ),
    );

    if (countries.length === 0) {
      return [];
    }

    const minYear = this.parseYear(params.from);
    const maxYear = this.parseYear(params.to);
    const [fromYear, toYear] =
      minYear != null && maxYear != null && minYear > maxYear
        ? [maxYear, minYear]
        : [minYear, maxYear];

    const tableRef = this.getGoldTableRefOrThrow(indicator.gold_table);
    const column = this.ensureSafeIdentifier(indicator.gold_column, 'indicator column');
    const canUseTrend =
      Boolean(indicator.supports_trend) && Boolean(indicator.analytics_table);
    const trendSql = canUseTrend
      ? `a.${this.ensureSafeIdentifier(`${indicator.code}_trend`, 'trend column')}`
      : 'CAST(NULL AS FLOAT64)';
    const analyticsJoinSql = canUseTrend
      ? `LEFT JOIN \`${this.getAnalyticsTableRefOrThrow(indicator.analytics_table)}\` a
        ON g.country_code = a.country_code AND g.year = a.year`
      : '';

    const sql = `
      SELECT
        g.country_code AS country_code,
        COALESCE(g.country, g.country_code) AS country,
        g.year AS year,
        @indicator AS indicator,
        @indicatorName AS indicator_name,
        @category AS category,
        @unit AS unit,
        g.${column} AS value,
        ${trendSql} AS trend_value
      FROM \`${tableRef}\` g
      ${analyticsJoinSql}
      WHERE g.country_code IN UNNEST(@countries)
        AND (@fromYear IS NULL OR g.year >= @fromYear)
        AND (@toYear IS NULL OR g.year <= @toYear)
      ORDER BY g.year ASC, g.country_code ASC
      LIMIT @limit
    `;

    const rows = await this.executeQuery<BigQueryCompareRow>(sql, {
      countries,
      fromYear,
      toYear,
      indicator: indicator.code,
      indicatorName: indicator.name_vi || indicator.name_en || indicator.code,
      category: indicator.category,
      unit: indicator.unit || '',
      limit: Math.min(MAX_LIMIT * 10, 2000),
    });

    return rows.map(row => ({
      ...row,
      year: Number(row.year),
      value: row.value == null ? null : Number(row.value),
      trend_value: row.trend_value == null ? null : Number(row.trend_value),
    }));
  }

  async getCountryIndicators(
    countryCode: string,
  ): Promise<BigQueryCountryIndicatorsResponse> {
    const normalizedCountryCode = this.normalizeCountryCode(countryCode);
    if (!normalizedCountryCode) {
      throw new BadRequestException('Mã quốc gia không hợp lệ. Yêu cầu mã ISO3.');
    }

    const eligibleIndicators = this.indicators.filter(
      indicator =>
        indicator.supports_raw &&
        indicator.gold_table &&
        indicator.gold_column &&
        indicator.code !== 'decade' &&
        indicator.code !== 'flag_score' &&
        indicator.code !== 'completeness_score',
    );

    const indicatorsByTable = new Map<string, GeneratedIndicatorContract[]>();
    eligibleIndicators.forEach(indicator => {
      const table = indicator.gold_table as string;
      if (!indicatorsByTable.has(table)) {
        indicatorsByTable.set(table, []);
      }
      indicatorsByTable.get(table)!.push(indicator);
    });

    const rows: BigQueryCountryIndicatorRow[] = [];
    for (const [tableName, tableIndicators] of indicatorsByTable.entries()) {
      const tableRef = this.getGoldTableRefOrThrow(tableName);
      const safeColumns = tableIndicators.map(indicator =>
        this.ensureSafeIdentifier(indicator.gold_column, 'indicator column'),
      );
      const distinctColumns = Array.from(new Set(safeColumns));
      const selectedColumns = distinctColumns
        .map(column => `g.${column} AS ${column}`)
        .join(',\n        ');

      const sql = `
        SELECT
          g.country_code AS country_code,
          COALESCE(g.country, g.country_code) AS country,
          g.year AS year,
          ${selectedColumns}
        FROM \`${tableRef}\` g
        WHERE g.country_code = @countryCode
        ORDER BY g.year ASC
        LIMIT @limit
      `;

      const tableRows = await this.executeQuery<Record<string, unknown>>(sql, {
        countryCode: normalizedCountryCode,
        limit: Math.min(MAX_LIMIT * 10, 5000),
      });

      const analyticsIndicators = tableIndicators.filter(
        indicator => indicator.analytics_table,
      );
      const analyticsByKey = new Map<string, Record<string, unknown>>();
      if (analyticsIndicators.length > 0) {
        const analyticsTable = analyticsIndicators[0].analytics_table;
        const allSameAnalyticsTable = analyticsIndicators.every(
          indicator => indicator.analytics_table === analyticsTable,
        );
        if (analyticsTable && allSameAnalyticsTable) {
          const analyticsTableRef = this.getAnalyticsTableRefOrThrow(analyticsTable);
          const analyticsColumns = Array.from(
            new Set(
              analyticsIndicators.flatMap(indicator => {
                const base = this.ensureSafeIdentifier(
                  indicator.code,
                  'indicator code',
                );
                return [
                  `${base}_trend`,
                  `${base}_residual`,
                  `${base}_anomaly_score`,
                ].map(column =>
                  this.ensureSafeIdentifier(column, 'analytics column'),
                );
              }),
            ),
          );
          const analyticsSelectedColumns = analyticsColumns
            .map(column => `a.${column} AS ${column}`)
            .join(',\n          ');
          const analyticsSql = `
            SELECT
              a.country_code AS country_code,
              a.year AS year,
              ${analyticsSelectedColumns}
            FROM \`${analyticsTableRef}\` a
            WHERE a.country_code = @countryCode
            ORDER BY a.year ASC
            LIMIT @limit
          `;
          const analyticsRows = await this.executeQuery<Record<string, unknown>>(
            analyticsSql,
            {
              countryCode: normalizedCountryCode,
              limit: Math.min(MAX_LIMIT * 10, 5000),
            },
          );
          analyticsRows.forEach(analyticsRow => {
            const key = `${String(analyticsRow.country_code)}-${Number(
              analyticsRow.year,
            )}`;
            analyticsByKey.set(key, analyticsRow);
          });
        }
      }

      tableRows.forEach(row => {
        tableIndicators.forEach(indicator => {
          const rawValue = row[indicator.gold_column];
          const analyticsKey = `${String(
            row.country_code || normalizedCountryCode,
          )}-${Number(row.year)}`;
          const analyticsRow = analyticsByKey.get(analyticsKey);
          const safeIndicatorCode = this.ensureSafeIdentifier(
            indicator.code,
            'indicator code',
          );
          const trendColumn = `${safeIndicatorCode}_trend`;
          const residualColumn = `${safeIndicatorCode}_residual`;
          const anomalyColumn = `${safeIndicatorCode}_anomaly_score`;
          const trendRaw =
            indicator.supports_trend && indicator.analytics_table && analyticsRow
              ? (analyticsRow as unknown as Record<string, unknown>)[trendColumn]
              : null;
          const residualRaw =
            indicator.supports_trend && indicator.analytics_table && analyticsRow
              ? (analyticsRow as unknown as Record<string, unknown>)[residualColumn]
              : null;
          const anomalyRaw =
            indicator.supports_anomaly && indicator.analytics_table && analyticsRow
              ? (analyticsRow as unknown as Record<string, unknown>)[anomalyColumn]
              : null;
          const trendValue =
            trendRaw == null || Number.isNaN(Number(trendRaw))
              ? null
              : Number(trendRaw);
          const residualValue =
            residualRaw == null || Number.isNaN(Number(residualRaw))
              ? null
              : Number(residualRaw);
          const anomalyScore =
            anomalyRaw == null || Number.isNaN(Number(anomalyRaw))
              ? null
              : Number(anomalyRaw);
          rows.push({
            country_code: String(row.country_code || normalizedCountryCode),
            country: String(row.country || normalizedCountryCode),
            year: Number(row.year),
            indicator: indicator.code,
            indicator_name: indicator.name_vi || indicator.name_en || indicator.code,
            category: indicator.category,
            unit: indicator.unit || '',
            value:
              rawValue == null || Number.isNaN(Number(rawValue))
                ? rawValue == null
                  ? null
                  : null
                : Number(rawValue),
            supports_trend: Boolean(indicator.supports_trend),
            supports_anomaly: Boolean(indicator.supports_anomaly),
            trend_value: indicator.supports_trend ? trendValue : null,
            residual_value: indicator.supports_trend ? residualValue : null,
            anomaly_score: indicator.supports_anomaly ? anomalyScore : null,
            is_anomaly:
              indicator.supports_anomaly && anomalyScore != null
                ? anomalyScore >= 0.75
                : false,
            source_table: tableName,
          });
        });
      });
    }

    const orderedRows = rows.sort((a, b) => {
      if (a.indicator !== b.indicator) {
        return a.indicator.localeCompare(b.indicator);
      }
      return a.year - b.year;
    });

    const summaryByIndicator = new Map<
      string,
      {
        total: number;
        nonNull: number;
        latestYear: number | null;
        latestValue: number | null;
      }
    >();

    orderedRows.forEach(row => {
      const current = summaryByIndicator.get(row.indicator) || {
        total: 0,
        nonNull: 0,
        latestYear: null,
        latestValue: null,
      };
      current.total += 1;
      if (row.value != null) {
        current.nonNull += 1;
        if (current.latestYear == null || row.year >= current.latestYear) {
          current.latestYear = row.year;
          current.latestValue = row.value;
        }
      }
      summaryByIndicator.set(row.indicator, current);
    });

    const summary = Array.from(summaryByIndicator.entries())
      .map(([indicator, value]) => ({
        indicator,
        latest_non_null_year: value.latestYear,
        latest_non_null_value: value.latestValue,
        coverage_ratio:
          value.total === 0
            ? 0
            : Number((value.nonNull / value.total).toFixed(4)),
      }))
      .sort((a, b) => a.indicator.localeCompare(b.indicator));

    return {
      country_code: normalizedCountryCode,
      rows: orderedRows,
      summary,
    };
  }

  async getClusterBenchmark(
    countryCode: string,
    indicator: string,
    year?: number | null,
  ): Promise<BigQueryClusterBenchmarkResponse | null> {
    const normalizedCountryCode = this.normalizeCountryCode(countryCode);
    if (!normalizedCountryCode) {
      return null;
    }

    const indicatorSql =
      indicator === 'rGDP_growth_YoY' || indicator === 'actual_growth'
        ? 'g.rGDP_growth_YoY'
        : indicator === 'govdebt_GDP' || indicator === 'actual_debt'
          ? 'an_fiscal.govdebt_GDP_actual'
          : indicator === 'REER_deviation' || indicator === 'actual_reer_deviation'
            ? 'an_risk.REER_deviation_actual'
            : null;

    if (!indicatorSql) {
      return null;
    }

    const sql = `
      WITH current_cluster AS (
        SELECT
          c.cluster_id AS cluster_id,
          c.year AS year
        FROM \`${this.tables.analyticsClusters}\` c
        WHERE c.country_code = @countryCode
          AND (@year IS NULL OR c.year = @year)
        ORDER BY c.year DESC
        LIMIT 1
      ),
      members AS (
        SELECT
          c.country_code AS country_code,
          c.country AS country_name,
          c.year AS year
        FROM \`${this.tables.analyticsClusters}\` c
        JOIN current_cluster cc
          ON c.cluster_id = cc.cluster_id AND c.year = cc.year
      )
      SELECT
        cc.cluster_id AS cluster_id,
        cc.year AS year,
        @indicator AS indicator,
        m.country_code AS country_code,
        m.country_name AS country_name,
        ${indicatorSql} AS value
      FROM members m
      JOIN current_cluster cc
        ON m.year = cc.year
      LEFT JOIN \`${this.tables.goldGrowthDynamics}\` g
        ON m.country_code = g.country_code AND m.year = g.year
      LEFT JOIN \`${this.tables.analyticsGoldFiscalMonetary}\` an_fiscal
        ON m.country_code = an_fiscal.country_code AND m.year = an_fiscal.year
      LEFT JOIN \`${this.tables.analyticsGoldCrisisRisk}\` an_risk
        ON m.country_code = an_risk.country_code AND m.year = an_risk.year
      ORDER BY m.country_code ASC
      LIMIT @limit
    `;

    const rows = await this.executeQuery<
      {
        cluster_id: number;
        year: number;
        indicator: string;
        country_code: string;
        country_name: string;
        value: number | null;
      }
    >(sql, {
      countryCode: normalizedCountryCode,
      year: year ?? null,
      indicator,
      limit: MAX_LIMIT,
    });

    if (rows.length === 0) {
      return null;
    }

    const average =
      rows.reduce((sum, row) => sum + (Number(row.value) || 0), 0) / rows.length;

    return {
      cluster_id: Number(rows[0].cluster_id),
      indicator,
      year: Number(rows[0].year),
      average,
      members: rows.map(row => ({
        country_code: row.country_code,
        country_name: row.country_name || row.country_code,
        year: Number(row.year),
        value: row.value ?? null,
      })),
    };
  }

  async getClusters(year: number): Promise<BigQueryClusterItem[]> {
    const safeYear = Number(year);
    const sql = `
      SELECT
        c.country_code AS country_code,
        c.country AS country,
        c.year AS year,
        c.cluster_id AS cluster_id,
        c.latest_valid_year AS latest_valid_year
      FROM \`${this.tables.analyticsClusters}\` c
      WHERE c.year = @year
      ORDER BY c.country_code ASC
      LIMIT @limit
    `;
    return this.executeQuery<BigQueryClusterItem>(sql, {
      year: safeYear,
      limit: MAX_LIMIT,
    });
  }

  async getAnomalies(
    params: BigQueryAnomaliesParams,
  ): Promise<{ items: BigQueryAnomalyItem[]; meta: { total_count: number; limit: number; offset: number } }> {
    const hasIndicatorFilter =
      params.indicator !== undefined &&
      params.indicator !== null &&
      params.indicator.trim() !== '';
    const normalizedIndicator = this.normalizeAnomalyIndicator(params.indicator);
    const normalizedCountryCode = this.normalizeCountryCode(params.countryCode);
    const threshold = this.clampNumber(params.threshold, 0, 1, 0.75);
    const limit = this.clampNumber(params.limit, 1, MAX_LIMIT, 15);
    const offset = this.clampNumber(params.offset, 0, Number.MAX_SAFE_INTEGER, 0);

    if (hasIndicatorFilter && !normalizedIndicator) {
      const supportedCodes = Array.from(this.anomalyIndicatorsByCode.keys()).sort();
      throw new BadRequestException(
        `Chỉ số anomaly không hỗ trợ. Các mã hợp lệ: ${supportedCodes.join(', ')}`,
      );
    }

    const selectedIndicators = normalizedIndicator
      ? [this.anomalyIndicatorsByCode.get(normalizedIndicator)!]
      : Array.from(this.anomalyIndicatorsByCode.values());
    if (selectedIndicators.length === 0) {
      return {
        items: [],
        meta: { total_count: 0, limit, offset },
      };
    }

    const anomalyBranches: string[] = [];
    const countryFilterSql = normalizedCountryCode
      ? 'AND a.country_code = @countryCode'
      : '';

    selectedIndicators.forEach(indicator => {
      const analyticsTableRef = this.getAnalyticsTableRefOrThrow(
        indicator.analytics_table,
      );
      const baseColumn = this.ensureSafeIdentifier(
        indicator.gold_column,
        'indicator column',
      );
      const actualColumn = this.ensureSafeIdentifier(
        `${baseColumn}_actual`,
        'actual column',
      );
      const anomalyColumn = this.ensureSafeIdentifier(
        `${baseColumn}_anomaly_score`,
        'anomaly score column',
      );

      anomalyBranches.push(`
        SELECT
          a.country_code AS country_code,
          a.year AS year,
          '${indicator.code}' AS indicator,
          a.${actualColumn} AS actual_value,
          a.${anomalyColumn} AS anomaly_score,
          g.country AS country_name
        FROM \`${analyticsTableRef}\` a
        LEFT JOIN \`${this.tables.goldGrowthDynamics}\` g
          ON g.country_code = a.country_code AND g.year = a.year
        WHERE a.${anomalyColumn} BETWEEN @threshold AND 1
          ${countryFilterSql}
      `);
    });

    const sql = `
      WITH anomaly_raw AS (
        ${anomalyBranches.join('\nUNION ALL\n')}
      ),
      dedup AS (
        SELECT
          country_code,
          year,
          indicator,
          actual_value,
          anomaly_score,
          country_name,
          ROW_NUMBER() OVER (
            PARTITION BY country_code, year, indicator
            ORDER BY anomaly_score DESC
          ) AS rn
        FROM anomaly_raw
      ),
      ranked AS (
        SELECT
          country_code,
          year,
          indicator,
          actual_value,
          anomaly_score,
          COALESCE(country_name, country_code) AS country_name
        FROM dedup
        WHERE rn = 1
      )
      SELECT
        country_code,
        year,
        indicator,
        actual_value,
        anomaly_score,
        country_name,
        COUNT(*) OVER() AS total_count
      FROM ranked
      ORDER BY anomaly_score DESC, year DESC
      LIMIT @limit
      OFFSET @offset
    `;

    const queryParams: Record<string, unknown> = {
      threshold,
      limit,
      offset,
    };
    if (normalizedCountryCode) {
      queryParams.countryCode = normalizedCountryCode;
    }

    const rows = await this.executeQuery<
      BigQueryAnomalyItem & { total_count: number | string | null }
    >(sql, queryParams);

    const totalCount =
      rows.length > 0 ? Number(rows[0].total_count || 0) : 0;

    return {
      items: rows.map(row => ({
        country_code: row.country_code,
        year: Number(row.year),
        indicator: row.indicator,
        actual_value: row.actual_value == null ? null : Number(row.actual_value),
        anomaly_score:
          row.anomaly_score == null ? null : Number(row.anomaly_score),
        country_name: row.country_name,
      })),
      meta: {
        total_count: totalCount,
        limit,
        offset,
      },
    };
  }

  private buildTableRef(dataset: string, table: string): string {
    return `${this.projectId}.${dataset}.${table}`;
  }

  private getGoldTableRefOrThrow(tableName: string | null): string {
    if (!tableName) {
      throw new BadRequestException('Chỉ số không có bảng Gold hợp lệ.');
    }
    const safeTable = this.ensureSafeIdentifier(tableName, 'gold table');
    const tableRef = this.buildTableRef(this.goldDataset, safeTable);
    if (!this.whitelistedTables.has(tableRef)) {
      throw new BadRequestException(`Bảng Gold không được phép truy vấn: ${safeTable}`);
    }
    return tableRef;
  }

  private getAnalyticsTableRefOrThrow(tableName: string | null): string {
    if (!tableName) {
      throw new BadRequestException('Chỉ số không có bảng Analytics hợp lệ.');
    }
    const safeTable = this.ensureSafeIdentifier(tableName, 'analytics table');
    const tableRef = this.buildTableRef(this.analyticsDataset, safeTable);
    if (!this.whitelistedTables.has(tableRef)) {
      throw new BadRequestException(
        `Bảng Analytics không được phép truy vấn: ${safeTable}`,
      );
    }
    return tableRef;
  }

  private getComparableIndicatorOrThrow(
    indicatorCode: string,
  ): GeneratedIndicatorContract {
    const contract = getIndicator(indicatorCode);
    if (!contract) {
      throw new BadRequestException(`Chỉ số không tồn tại trong contract: ${indicatorCode}`);
    }
    if (
      !contract.supports_compare ||
      !contract.supports_raw ||
      !contract.gold_table ||
      !contract.gold_column
    ) {
      throw new BadRequestException(
        `Chỉ số ${indicatorCode} chưa hỗ trợ so sánh theo contract hiện tại.`,
      );
    }
    return contract;
  }

  private ensureSafeIdentifier(input: string, label: string): string {
    if (!SAFE_IDENTIFIER_PATTERN.test(input)) {
      throw new BadRequestException(`${label} không hợp lệ: ${input}`);
    }
    return input;
  }

  private async executeQuery<T>(
    query: string,
    params: Record<string, unknown>,
  ): Promise<T[]> {
    this.validateQuerySafety(query);
    const cacheKey = `${query}::${JSON.stringify(params)}`;
    const cached = this.cacheService.get<T[]>(cacheKey);
    if (cached) {
      return cached;
    }

    const [rows] = await this.client.query({
      query,
      params,
      location: this.location,
      useLegacySql: false,
      maximumBytesBilled: String(this.maximumBytesBilled),
    });

    const typedRows = rows as T[];
    this.cacheService.set(cacheKey, typedRows, this.cacheTtlSeconds);
    return typedRows;
  }

  private validateQuerySafety(query: string): void {
    if (/\bselect\s+\*/i.test(query)) {
      throw new Error('Unsafe query rejected: SELECT * is not allowed.');
    }

    const tableRefs = Array.from(query.matchAll(/`([^`]+)`/g)).map(
      match => match[1],
    );
    if (tableRefs.length === 0) {
      throw new Error('Unsafe query rejected: missing fully-qualified tables.');
    }

    for (const tableRef of tableRefs) {
      if (!this.whitelistedTables.has(tableRef)) {
        throw new Error(
          `Unsafe query rejected: table ${tableRef} is not whitelisted.`,
        );
      }
    }
  }

  private clampNumber(
    value: number | undefined,
    min: number,
    max: number,
    fallback: number,
  ): number {
    const normalized = Number.isFinite(Number(value)) ? Number(value) : fallback;
    return Math.min(max, Math.max(min, normalized));
  }

  private normalizeAnomalyIndicator(indicator?: string): string | undefined {
    if (!indicator) {
      return undefined;
    }

    const canonicalByCode = this.anomalyIndicatorsByCode.get(indicator.trim());
    if (canonicalByCode) {
      return canonicalByCode.code;
    }

    const normalized = indicator.trim().toLowerCase();
    const aliasResolved = ANOMALY_ALIAS_MAP[normalized];
    if (aliasResolved && this.anomalyIndicatorsByCode.has(aliasResolved)) {
      return aliasResolved;
    }

    return undefined;
  }

  private normalizeCountryCode(countryCode?: string): string | undefined {
    if (!countryCode) {
      return undefined;
    }

    const normalized = countryCode.trim().toUpperCase();
    if (!/^[A-Z]{3}$/.test(normalized)) {
      return undefined;
    }
    return normalized;
  }

  private parseYear(value?: number): number | null {
    if (value == null) {
      return null;
    }
    const year = Number(value);
    if (!Number.isFinite(year)) {
      return null;
    }
    return Math.trunc(year);
  }

  private normalizeCompletenessRatio(value?: number | null): number | null {
    if (value == null) {
      return null;
    }
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      return null;
    }
    if (numeric < 0) {
      return 0;
    }
    if (numeric <= 1) {
      return numeric;
    }
    if (numeric <= 100) {
      return numeric / 100;
    }
    return 1;
  }
}
