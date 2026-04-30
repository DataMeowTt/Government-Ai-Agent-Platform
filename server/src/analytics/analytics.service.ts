import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository, Between } from 'typeorm';
import { AnalyticsClusters } from '../entities/analytics-clusters.entity';
import { AnalyticsGoldGrowthDynamics } from '../entities/analytics-gold-growth-dynamics.entity';
import { AnalyticsGoldFiscalMonetary } from '../entities/analytics-gold-fiscal-monetary.entity';
import { AnalyticsGoldCrisisRisk } from '../entities/analytics-gold-crisis-risk.entity';
import { GoldGrowthDynamics } from '../entities/gold-growth-dynamics.entity';

interface AnomalyItem {
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
    @InjectRepository(AnalyticsClusters)
    private clustersRepo: Repository<AnalyticsClusters>,
    @InjectRepository(AnalyticsGoldGrowthDynamics)
    private growthAnalyticsRepo: Repository<AnalyticsGoldGrowthDynamics>,
    @InjectRepository(AnalyticsGoldFiscalMonetary)
    private fiscalAnalyticsRepo: Repository<AnalyticsGoldFiscalMonetary>,
    @InjectRepository(AnalyticsGoldCrisisRisk)
    private riskAnalyticsRepo: Repository<AnalyticsGoldCrisisRisk>,
    @InjectRepository(GoldGrowthDynamics)
    private growthRepo: Repository<GoldGrowthDynamics>,
  ) { }

  async getClusters(year: number) {
    return this.clustersRepo.find({
      where: { year },
      order: { country_code: 'ASC' },
    });
  }

  async getAnomalies(
    countryCode?: string,
    indicator?: string,
    threshold: number = 0.75,
    limit: number = 100,
  ) {
    const anomalySources: AnomalyItem[] = [];

    if (!indicator || indicator === 'growth') {
      const growthAnomalies = await this.growthAnalyticsRepo.find({
        where: {
          ...(countryCode && { country_code: countryCode }),
          rGDP_growth_YoY_anomaly_score: Between(threshold, 1),
        },
        select: ['country_code', 'year', 'rGDP_growth_YoY_actual', 'rGDP_growth_YoY_anomaly_score'],
      });
      growthAnomalies.forEach(a => {
        anomalySources.push({
          country_code: a.country_code,
          year: a.year,
          indicator: 'rGDP_growth_YoY',
          actual_value: a.rGDP_growth_YoY_actual,
          anomaly_score: a.rGDP_growth_YoY_anomaly_score,
        });
      });
    }

    if (!indicator || indicator === 'govdebt') {
      const debtAnomalies = await this.fiscalAnalyticsRepo.find({
        where: {
          ...(countryCode && { country_code: countryCode }),
          govdebt_GDP_anomaly_score: Between(threshold, 1),
        },
        select: ['country_code', 'year', 'govdebt_GDP_actual', 'govdebt_GDP_anomaly_score'],
      });
      debtAnomalies.forEach(a => {
        anomalySources.push({
          country_code: a.country_code,
          year: a.year,
          indicator: 'govdebt_GDP',
          actual_value: a.govdebt_GDP_actual,
          anomaly_score: a.govdebt_GDP_anomaly_score,
        });
      });
    }

    if (!indicator || indicator === 'reer') {
      const reerAnomalies = await this.riskAnalyticsRepo.find({
        where: {
          ...(countryCode && { country_code: countryCode }),
          REER_deviation_anomaly_score: Between(threshold, 1),
        },
        select: ['country_code', 'year', 'REER_deviation_actual', 'REER_deviation_anomaly_score'],
      });
      reerAnomalies.forEach(a => {
        anomalySources.push({
          country_code: a.country_code,
          year: a.year,
          indicator: 'REER_deviation',
          actual_value: a.REER_deviation_actual,
          anomaly_score: a.REER_deviation_anomaly_score,
        });
      });
    }

    const countryNames = await this.growthRepo
      .createQueryBuilder('g')
      .select(['g.country_code', 'g.country'])
      .distinct(true)
      .getRawMany();
    const nameMap = new Map(countryNames.map(c => [c.country_code, c.country]));

    const results = anomalySources.map(item => ({
      ...item,
      country_name: nameMap.get(item.country_code) || item.country_code,
    }));

    const sorted = results.sort((a, b) => (b.anomaly_score || 0) - (a.anomaly_score || 0));
    return {
      items: sorted.slice(0, limit),
      meta: { total_count: sorted.length },
    };
  }
}