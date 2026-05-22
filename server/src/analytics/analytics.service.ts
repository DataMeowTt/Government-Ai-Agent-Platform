import {
  BadRequestException,
  Injectable,
  InternalServerErrorException,
  Optional,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { ConfigService } from '@nestjs/config';
import { Repository, Between } from 'typeorm';
import { AnalyticsClusters } from '../entities/analytics-clusters.entity';
import { AnalyticsGoldGrowthDynamics } from '../entities/analytics-gold-growth-dynamics.entity';
import { AnalyticsGoldFiscalMonetary } from '../entities/analytics-gold-fiscal-monetary.entity';
import { AnalyticsGoldCrisisRisk } from '../entities/analytics-gold-crisis-risk.entity';
import { GoldGrowthDynamics } from '../entities/gold-growth-dynamics.entity';
import { BigQueryService } from '../bigquery/bigquery.service';
import { getIndicator } from '../generated/indicator-contract';

export interface AnomalyItem {
  country_code: string;
  year: number;
  indicator: string;
  actual_value: number | null;
  anomaly_score: number | null;
  country_name?: string;
}

@Injectable()
export class AnalyticsService {
  constructor(
    private readonly configService: ConfigService,
    private readonly bigQueryService: BigQueryService,
    @Optional()
    @InjectRepository(AnalyticsClusters)
    private clustersRepo?: Repository<AnalyticsClusters>,
    @Optional()
    @InjectRepository(AnalyticsGoldGrowthDynamics)
    private growthAnalyticsRepo?: Repository<AnalyticsGoldGrowthDynamics>,
    @Optional()
    @InjectRepository(AnalyticsGoldFiscalMonetary)
    private fiscalAnalyticsRepo?: Repository<AnalyticsGoldFiscalMonetary>,
    @Optional()
    @InjectRepository(AnalyticsGoldCrisisRisk)
    private riskAnalyticsRepo?: Repository<AnalyticsGoldCrisisRisk>,
    @Optional()
    @InjectRepository(GoldGrowthDynamics)
    private growthRepo?: Repository<GoldGrowthDynamics>,
  ) {}

  async getClusters(year: number) {
    if (this.isBigQueryMode()) {
      return this.bigQueryService.getClusters(year);
    }

    return this.getClustersRepo().find({
      where: { year },
      order: { country_code: 'ASC' },
    });
  }

  async getAnomalies(
    countryCode?: string,
    indicator?: string,
    threshold: number = 0.75,
    limit: number = 15,
    offset: number = 0,
  ) {
    if (this.isBigQueryMode()) {
      return this.bigQueryService.getAnomalies({
        countryCode,
        indicator,
        threshold,
        limit,
        offset,
      });
    }

    const normalizedIndicator = this.normalizeAnomalyIndicator(indicator);
    if (indicator && !normalizedIndicator) {
      throw new BadRequestException(
        'Chỉ số anomaly không hỗ trợ. Hãy dùng mã canonical như rGDP_growth_YoY, govdebt_GDP, REER_deviation.',
      );
    }

    const whereBase = { ...(countryCode && { country_code: countryCode }) };

    const [growthAnomalies] = await this.getGrowthAnalyticsRepo().findAndCount({
      where: { ...whereBase, rGDP_growth_YoY_anomaly_score: Between(threshold, 1) },
      select: ['country_code', 'year', 'rGDP_growth_YoY_actual', 'rGDP_growth_YoY_anomaly_score'],
    });
    const [debtAnomalies] = await this.getFiscalAnalyticsRepo().findAndCount({
      where: { ...whereBase, govdebt_GDP_anomaly_score: Between(threshold, 1) },
      select: ['country_code', 'year', 'govdebt_GDP_actual', 'govdebt_GDP_anomaly_score'],
    });
    const [reerAnomalies] = await this.getRiskAnalyticsRepo().findAndCount({
      where: { ...whereBase, REER_deviation_anomaly_score: Between(threshold, 1) },
      select: ['country_code', 'year', 'REER_deviation_actual', 'REER_deviation_anomaly_score'],
    });

    const anomalySources: AnomalyItem[] = [];
    if (!normalizedIndicator || normalizedIndicator === 'rGDP_growth_YoY') {
      growthAnomalies.forEach(a => anomalySources.push({ country_code: a.country_code, year: a.year, indicator: 'rGDP_growth_YoY', actual_value: a.rGDP_growth_YoY_actual, anomaly_score: a.rGDP_growth_YoY_anomaly_score }));
    }
    if (!normalizedIndicator || normalizedIndicator === 'govdebt_GDP') {
      debtAnomalies.forEach(a => anomalySources.push({ country_code: a.country_code, year: a.year, indicator: 'govdebt_GDP', actual_value: a.govdebt_GDP_actual, anomaly_score: a.govdebt_GDP_anomaly_score }));
    }
    if (!normalizedIndicator || normalizedIndicator === 'REER_deviation') {
      reerAnomalies.forEach(a => anomalySources.push({ country_code: a.country_code, year: a.year, indicator: 'REER_deviation', actual_value: a.REER_deviation_actual, anomaly_score: a.REER_deviation_anomaly_score }));
    }

    const countryNames = await this.getGrowthRepo()
      .createQueryBuilder('g')
      .select(['g.country_code', 'g.country'])
      .distinct(true)
      .getRawMany();
    const nameMap = new Map(countryNames.map(c => [c.country_code, c.country]));
    const results = anomalySources.map(item => ({
      ...item,
      country_name: nameMap.get(item.country_code) || item.country_code,
    }));

    const uniqueMap = new Map<string, AnomalyItem>();
    results.forEach(item => {
      const key = `${item.country_code}-${item.year}-${item.indicator}`;
      const existing = uniqueMap.get(key);
      if (!existing || (item.anomaly_score || 0) > (existing.anomaly_score || 0)) {
        uniqueMap.set(key, item);
      }
    });

    const sorted = Array.from(uniqueMap.values()).sort((a, b) => (b.anomaly_score || 0) - (a.anomaly_score || 0));

    const totalCount = sorted.length;
    const pagedItems = sorted.slice(offset, offset + limit);

    return {
      items: pagedItems,
      meta: { total_count: totalCount, limit, offset },
    };
  }

  private isBigQueryMode(): boolean {
    return this.configService.get<string>('BACKEND_DATA_SOURCE') === 'bigquery';
  }

  private getClustersRepo(): Repository<AnalyticsClusters> {
    if (!this.clustersRepo) {
      throw new InternalServerErrorException(
        'PostgreSQL repository unavailable: AnalyticsClusters repository is not configured.',
      );
    }
    return this.clustersRepo;
  }

  private getGrowthAnalyticsRepo(): Repository<AnalyticsGoldGrowthDynamics> {
    if (!this.growthAnalyticsRepo) {
      throw new InternalServerErrorException(
        'PostgreSQL repository unavailable: AnalyticsGoldGrowthDynamics repository is not configured.',
      );
    }
    return this.growthAnalyticsRepo;
  }

  private getFiscalAnalyticsRepo(): Repository<AnalyticsGoldFiscalMonetary> {
    if (!this.fiscalAnalyticsRepo) {
      throw new InternalServerErrorException(
        'PostgreSQL repository unavailable: AnalyticsGoldFiscalMonetary repository is not configured.',
      );
    }
    return this.fiscalAnalyticsRepo;
  }

  private getRiskAnalyticsRepo(): Repository<AnalyticsGoldCrisisRisk> {
    if (!this.riskAnalyticsRepo) {
      throw new InternalServerErrorException(
        'PostgreSQL repository unavailable: AnalyticsGoldCrisisRisk repository is not configured.',
      );
    }
    return this.riskAnalyticsRepo;
  }

  private getGrowthRepo(): Repository<GoldGrowthDynamics> {
    if (!this.growthRepo) {
      throw new InternalServerErrorException(
        'PostgreSQL repository unavailable: GoldGrowthDynamics repository is not configured.',
      );
    }
    return this.growthRepo;
  }

  private normalizeAnomalyIndicator(indicator?: string): string | undefined {
    if (!indicator) {
      return undefined;
    }

    const direct = getIndicator(indicator);
    if (direct?.supports_anomaly) {
      return direct.code;
    }

    const normalized = indicator.trim().toLowerCase();
    if (normalized === 'growth' || normalized === 'rgdp_growth_yoy') {
      return 'rGDP_growth_YoY';
    }
    if (normalized === 'govdebt' || normalized === 'govdebt_gdp') {
      return 'govdebt_GDP';
    }
    if (normalized === 'reer' || normalized === 'reer_deviation') {
      return 'REER_deviation';
    }
    return undefined;
  }
}
