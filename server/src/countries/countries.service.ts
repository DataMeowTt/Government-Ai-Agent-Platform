import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { GoldGrowthDynamics } from '../entities/gold-growth-dynamics.entity';
import { AnalyticsGoldGrowthDynamics } from '../entities/analytics-gold-growth-dynamics.entity';
import { AnalyticsGoldFiscalMonetary } from '../entities/analytics-gold-fiscal-monetary.entity';
import { AnalyticsGoldSocialWelfare } from '../entities/analytics-gold-social-welfare.entity';
import { AnalyticsClusters } from '../entities/analytics-clusters.entity';
import { AnalyticsGoldStructuralComposition } from '../entities/analytics-gold-structural-composition.entity';
import { AnalyticsGoldCrisisRisk } from '../entities/analytics-gold-crisis-risk.entity';
@Injectable()
export class CountriesService {
  constructor(
    @InjectRepository(GoldGrowthDynamics)
    private growthRepo: Repository<GoldGrowthDynamics>,
    @InjectRepository(AnalyticsGoldGrowthDynamics)
    private anGrowthRepo: Repository<AnalyticsGoldGrowthDynamics>,
  ) {}

  async getFullCountryAnalytics(countryCode: string) {
    const qb = this.growthRepo.createQueryBuilder('g');

    return qb
      .select([
        'g.country_code as country_code',
        'g.year as year',
        // Growth Group
        'g.rGDP_growth_YoY as actual_growth',
        'an_growth.rGDP_growth_YoY_trend as trend_growth',
        'an_growth.rGDP_growth_YoY_anomaly_score as anomaly_growth',
        // Fiscal Group
        'an_fiscal.govdebt_GDP_actual as actual_debt',
        'an_fiscal.govdebt_GDP_anomaly_score as anomaly_debt',
        'an_fiscal.inflation_cpi_actual as actual_inflation',
        // Social Group
        'an_social.poverty_headcount_actual as actual_poverty',
        'an_social.unemployment_total_actual as actual_unemployment',
        // Structure Group
        'an_struct.manuf_va_share_actual as actual_manuf_share',
        'an_struct.agri_va_share_actual as actual_agri_share',
        // Risk Group
        'an_risk.REER_deviation_actual as actual_reer_deviation',
        'an_risk.REER_deviation_anomaly_score as anomaly_reer_deviation',
        // Cluster Info
        'c.cluster_id as cluster_id'
      ])
      .leftJoin(AnalyticsGoldGrowthDynamics, 'an_growth', 'g.country_code = an_growth.country_code AND g.year = an_growth.year')
      .leftJoin(AnalyticsGoldFiscalMonetary, 'an_fiscal', 'g.country_code = an_fiscal.country_code AND g.year = an_fiscal.year')
      .leftJoin(AnalyticsGoldSocialWelfare, 'an_social', 'g.country_code = an_social.country_code AND g.year = an_social.year')
      .leftJoin(AnalyticsGoldStructuralComposition, 'an_struct', 'g.country_code = an_struct.country_code AND g.year = an_struct.year')
      .leftJoin(AnalyticsGoldCrisisRisk, 'an_risk', 'g.country_code = an_risk.country_code AND g.year = an_risk.year')
      .leftJoin(AnalyticsClusters, 'c', 'g.country_code = c.country_code AND g.year = c.year')
      .where('g.country_code = :countryCode', { countryCode })
      .orderBy('g.year', 'ASC')
      .getRawMany();
  }
}