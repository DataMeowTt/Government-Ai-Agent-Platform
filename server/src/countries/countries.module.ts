import { DynamicModule, Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { CountriesController } from './countries.controller';
import { CountriesService } from './countries.service';
import { GoldGrowthDynamics } from '../entities/gold-growth-dynamics.entity';
import { AnalyticsGoldGrowthDynamics } from '../entities/analytics-gold-growth-dynamics.entity';
import { AnalyticsGoldFiscalMonetary } from '../entities/analytics-gold-fiscal-monetary.entity';
import { AnalyticsGoldSocialWelfare } from '../entities/analytics-gold-social-welfare.entity';
import { AnalyticsGoldStructuralComposition } from '../entities/analytics-gold-structural-composition.entity';
import { AnalyticsGoldCrisisRisk } from '../entities/analytics-gold-crisis-risk.entity';
import { AnalyticsClusters } from '../entities/analytics-clusters.entity';
import { BigQueryModule } from '../bigquery/bigquery.module';

function createCountriesTypeOrmFeatureModule(): DynamicModule | undefined {
  if (process.env.BACKEND_DATA_SOURCE === 'bigquery') {
    return undefined;
  }

  return TypeOrmModule.forFeature([
    GoldGrowthDynamics,
    AnalyticsGoldGrowthDynamics,
    AnalyticsGoldFiscalMonetary,
    AnalyticsGoldSocialWelfare,
    AnalyticsGoldStructuralComposition,
    AnalyticsGoldCrisisRisk,
    AnalyticsClusters,
  ]);
}

const countriesTypeOrmFeatureModule = createCountriesTypeOrmFeatureModule();

@Module({
  imports: [
    BigQueryModule,
    ...(countriesTypeOrmFeatureModule ? [countriesTypeOrmFeatureModule] : []),
  ],
  controllers: [CountriesController],
  providers: [CountriesService],
})
export class CountriesModule {}
