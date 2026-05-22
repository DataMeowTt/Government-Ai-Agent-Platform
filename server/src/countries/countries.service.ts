import {
  BadRequestException,
  Injectable,
  InternalServerErrorException,
  Optional,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { ConfigService } from '@nestjs/config';
import { Repository } from 'typeorm';
import { GoldGrowthDynamics } from '../entities/gold-growth-dynamics.entity';
import { AnalyticsGoldGrowthDynamics } from '../entities/analytics-gold-growth-dynamics.entity';
import { AnalyticsGoldFiscalMonetary } from '../entities/analytics-gold-fiscal-monetary.entity';
import { AnalyticsGoldSocialWelfare } from '../entities/analytics-gold-social-welfare.entity';
import { AnalyticsClusters } from '../entities/analytics-clusters.entity';
import { AnalyticsGoldStructuralComposition } from '../entities/analytics-gold-structural-composition.entity';
import { AnalyticsGoldCrisisRisk } from '../entities/analytics-gold-crisis-risk.entity';
import { GoldStructuralComposition } from '../entities/gold-structural-composition.entity';
import { BigQueryService } from '../bigquery/bigquery.service';
import { listIndicators } from '../generated/indicator-contract';
@Injectable()
export class CountriesService {
  constructor(
    private readonly configService: ConfigService,
    private readonly bigQueryService: BigQueryService,
    @Optional()
    @InjectRepository(GoldGrowthDynamics)
    private growthRepo?: Repository<GoldGrowthDynamics>,
    @Optional()
    @InjectRepository(AnalyticsGoldGrowthDynamics)
    private anGrowthRepo?: Repository<AnalyticsGoldGrowthDynamics>,
    @Optional()
    @InjectRepository(AnalyticsClusters)
    private clustersRepo?: Repository<AnalyticsClusters>,
  ) { }
  async getCountryAnomalies(countryCode: string, threshold: number = 0.75) {
    const analyticsPayload = await this.getFullCountryAnalytics(countryCode);
    const anomalies: any[] = [];

    analyticsPayload.data.forEach(row => {
      const events: Array<{ type: string; score: number; actual: number }> = [];

      if (row.anomaly_growth >= threshold) {
        events.push({ type: 'Sốc Tăng trưởng', score: row.anomaly_growth, actual: row.actual_growth });
      }
      if (row.anomaly_debt >= threshold) {
        events.push({ type: 'Cảnh báo Nợ công', score: row.anomaly_debt, actual: row.actual_debt });
      }
      if (row.anomaly_reer_deviation >= threshold) {
        events.push({ type: 'Rủi ro Tiền tệ', score: row.anomaly_reer_deviation, actual: row.actual_reer_deviation });
      }

      if (events.length > 0) {
        anomalies.push({
          year: row.year,
          events: events
        });
      }
    });

    return anomalies;
  }

  async triggerAnalyticsWorker() {
    try {
      const response = await fetch('http://localhost:8001/analytics/run-all', {
        method: 'POST',
      });
      const data = await response.json();
      return data;
    } catch (error) {
      throw new Error(`Không thể kết nối đến Analytics Worker: ${error.message}`);
    }
  }
  async findAll() {
    if (this.isBigQueryMode()) {
      return this.bigQueryService.listCountries();
    }

    const growthRepo = this.getGrowthRepo();
    const results = await growthRepo
      .createQueryBuilder('g')
      .select([
        'g.country_code as country_code',
        'g.country as country_name',
        'g.income_group as region',
      ])
      .distinct(true)
      .orderBy('g.country', 'ASC')
      .getRawMany();

    const deduped = new Map<
      string,
      { country_code: string; country_name: string; region: string | null }
    >();
    results.forEach(row => {
      const current = deduped.get(row.country_code);
      if (!current) {
        deduped.set(row.country_code, row);
        return;
      }
      if ((!current.region || current.region === 'N/A') && row.region) {
        deduped.set(row.country_code, row);
      }
    });

    return Array.from(deduped.values()).sort((a, b) =>
      a.country_name.localeCompare(b.country_name),
    );
  }

  private isBigQueryMode(): boolean {
    return this.configService.get<string>('BACKEND_DATA_SOURCE') === 'bigquery';
  }

  async getFullCountryAnalytics(countryCode: string) {
    if (this.isBigQueryMode()) {
      return this.bigQueryService.getFullCountryAnalytics(countryCode);
    }

    const growthRepo = this.getGrowthRepo();
    const qb = growthRepo.createQueryBuilder('g');
    const rows = await qb
      .select([
        'g.country_code as country_code', 'g.year as year',
        'g.rGDP_growth_YoY as actual_growth', 'an_growth.rGDP_growth_YoY_trend as trend_growth', 'an_growth.rGDP_growth_YoY_anomaly_score as anomaly_growth',
        'an_fiscal.govdebt_GDP_actual as actual_debt', 'an_fiscal.govdebt_GDP_anomaly_score as anomaly_debt', 'an_fiscal.inflation_cpi_actual as actual_inflation',
        'an_social.poverty_headcount_actual as actual_poverty', 'an_social.unemployment_total_actual as actual_unemployment',
        'an_struct.manuf_va_share_actual as actual_manuf_share', 'an_struct.agri_va_share_actual as actual_agri_share',
        'an_risk.REER_deviation_actual as actual_reer_deviation', 'an_risk.REER_deviation_anomaly_score as anomaly_reer_deviation',
        'c.cluster_id as cluster_id',
        'g.completeness_score as completeness_score',
        'COALESCE(gold_struct.flag_score, 0) as flag_score'
      ])
      .leftJoin(AnalyticsGoldGrowthDynamics, 'an_growth', 'g.country_code = an_growth.country_code AND g.year = an_growth.year')
      .leftJoin(AnalyticsGoldFiscalMonetary, 'an_fiscal', 'g.country_code = an_fiscal.country_code AND g.year = an_fiscal.year')
      .leftJoin(AnalyticsGoldSocialWelfare, 'an_social', 'g.country_code = an_social.country_code AND g.year = an_social.year')
      .leftJoin(AnalyticsGoldStructuralComposition, 'an_struct', 'g.country_code = an_struct.country_code AND g.year = an_struct.year')
      .leftJoin(GoldStructuralComposition, 'gold_struct', 'g.country_code = gold_struct.country_code AND g.year = gold_struct.year')
      .leftJoin(AnalyticsGoldCrisisRisk, 'an_risk', 'g.country_code = an_risk.country_code AND g.year = an_risk.year')
      .leftJoin(AnalyticsClusters, 'c', 'g.country_code = c.country_code AND g.year = c.year')
      .where('g.country_code = :countryCode', { countryCode })
      .orderBy('g.year', 'ASC')
      .getRawMany();

    const completenessRatio = rows.length > 0
      ? rows.reduce((sum, r) => {
          const normalized = this.normalizeCompletenessRatio(r.completeness_score);
          return sum + (normalized ?? 0);
        }, 0) / rows.length
      : null;
    const completenessPercent =
      completenessRatio == null ? null : Number((completenessRatio * 100).toFixed(2));
    const latestFlag = rows.length > 0 ? rows[rows.length - 1].flag_score : 0;

    return {
      meta: {
        country_code: countryCode,
        data_completeness_ratio:
          completenessRatio == null ? null : Number(completenessRatio.toFixed(4)),
        data_completeness_percent: completenessPercent,
        data_completeness: completenessPercent ?? 0,
        flag_score: Number(latestFlag) || 0,
        latest_year: rows.length > 0 ? rows[rows.length - 1].year : null
      },
      data: rows
    };
  }

  async getCountryIndicators(countryCode: string) {
    if (!/^[A-Z]{3}$/.test(countryCode)) {
      throw new BadRequestException('Mã quốc gia không hợp lệ. Yêu cầu mã ISO3.');
    }

    if (this.isBigQueryMode()) {
      return this.bigQueryService.getCountryIndicators(countryCode);
    }

    const growthRepo = this.getGrowthRepo();
    const indicators = listIndicators().filter(
      indicator => indicator.supports_raw && indicator.gold_table && indicator.gold_column,
    );
    const indicatorsByTable = new Map<string, typeof indicators>();
    indicators.forEach(indicator => {
      const table = indicator.gold_table as string;
      const existing = indicatorsByTable.get(table) || [];
      existing.push(indicator);
      indicatorsByTable.set(table, existing);
    });

    const rows: Array<{
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
    }> = [];

    for (const [table, tableIndicators] of indicatorsByTable.entries()) {
      const safeTable = this.ensureSafeIdentifier(table);
      const safeColumns = Array.from(
        new Set(tableIndicators.map(indicator => this.ensureSafeIdentifier(indicator.gold_column))),
      );
      const columnSql = safeColumns.map(column => `"${column}"`).join(', ');
      const sql = `
        SELECT country_code, country, year, ${columnSql}
        FROM "${safeTable}"
        WHERE country_code = $1
        ORDER BY year ASC
      `;
      const tableRows = await growthRepo.query(sql, [countryCode]);
      tableRows.forEach((tableRow: Record<string, unknown>) => {
        tableIndicators.forEach(indicator => {
          const rawValue = tableRow[indicator.gold_column];
          rows.push({
            country_code: String(tableRow.country_code || countryCode),
            country: String(tableRow.country || countryCode),
            year: Number(tableRow.year),
            indicator: indicator.code,
            indicator_name: indicator.name_vi || indicator.name_en || indicator.code,
            category: indicator.category,
            unit: indicator.unit || '',
            value:
              rawValue == null || Number.isNaN(Number(rawValue))
                ? null
                : Number(rawValue),
            supports_trend: Boolean(indicator.supports_trend),
            supports_anomaly: Boolean(indicator.supports_anomaly),
            trend_value: null,
            residual_value: null,
            anomaly_score: null,
            is_anomaly: false,
            source_table: safeTable,
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

    const summaryMap = new Map<
      string,
      { total: number; nonNull: number; latestYear: number | null; latestValue: number | null }
    >();

    orderedRows.forEach(row => {
      const summary = summaryMap.get(row.indicator) || {
        total: 0,
        nonNull: 0,
        latestYear: null,
        latestValue: null,
      };
      summary.total += 1;
      if (row.value != null) {
        summary.nonNull += 1;
        if (summary.latestYear == null || row.year >= summary.latestYear) {
          summary.latestYear = row.year;
          summary.latestValue = row.value;
        }
      }
      summaryMap.set(row.indicator, summary);
    });

    const summary = Array.from(summaryMap.entries())
      .map(([indicator, item]) => ({
        indicator,
        latest_non_null_year: item.latestYear,
        latest_non_null_value: item.latestValue,
        coverage_ratio: item.total === 0 ? 0 : Number((item.nonNull / item.total).toFixed(4)),
      }))
      .sort((a, b) => a.indicator.localeCompare(b.indicator));

    return {
      country_code: countryCode,
      rows: orderedRows,
      summary,
    };
  }
  async getClusterBenchmark(countryCode: string, indicator: string, year?: number | null) {
    if (this.isBigQueryMode()) {
      return this.bigQueryService.getClusterBenchmark(countryCode, indicator, year);
    }

    const clustersRepo = this.getClustersRepo();
    const growthRepo = this.getGrowthRepo();

    const currentCluster = await clustersRepo.findOne({
      where: { country_code: countryCode, year: year ?? undefined },
      order: { year: 'DESC' }
    });
    if (!currentCluster) throw new Error('Không tìm thấy cụm cho quốc gia này');

    const members = await clustersRepo.find({ where: { cluster_id: currentCluster.cluster_id, year: currentCluster.year } });
    const memberCodes = members.map(m => m.country_code);

    const qb = growthRepo.createQueryBuilder('g')
      .select(['g.country_code as country_code', 'g.country as country_name', 'g.year as year'])
      .where('g.country_code IN (:...codes)', { codes: memberCodes })
      .andWhere('g.year = :year', { year: currentCluster.year });

    if (indicator === 'rGDP_growth_YoY' || indicator === 'actual_growth') {
      qb.addSelect('g.rGDP_growth_YoY as value');
    } else if (indicator === 'govdebt_GDP' || indicator === 'actual_debt') {
      qb.addSelect('an_f.govdebt_GDP_actual as value').leftJoin(AnalyticsGoldFiscalMonetary, 'an_f', 'g.country_code = an_f.country_code AND g.year = an_f.year');
    } else if (indicator === 'actual_reer_deviation' || indicator === 'REER_deviation') {
      qb.addSelect('an_r.REER_deviation_actual as value').leftJoin(AnalyticsGoldCrisisRisk, 'an_r', 'g.country_code = an_r.country_code AND g.year = an_r.year');
    }

    const raw = await qb.getRawMany();
    const avg = raw.length > 0 ? raw.reduce((s, r) => s + (Number(r.value) || 0), 0) / raw.length : 0;
    return { cluster_id: currentCluster.cluster_id, indicator, year: currentCluster.year, average: avg, members: raw };
  }

  private getGrowthRepo(): Repository<GoldGrowthDynamics> {
    if (!this.growthRepo) {
      throw new InternalServerErrorException(
        'PostgreSQL repository unavailable: GoldGrowthDynamics repository is not configured.',
      );
    }
    return this.growthRepo;
  }

  private getClustersRepo(): Repository<AnalyticsClusters> {
    if (!this.clustersRepo) {
      throw new InternalServerErrorException(
        'PostgreSQL repository unavailable: AnalyticsClusters repository is not configured.',
      );
    }
    return this.clustersRepo;
  }

  private ensureSafeIdentifier(input: string): string {
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(input)) {
      throw new BadRequestException(`Định danh SQL không hợp lệ: ${input}`);
    }
    return input;
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
