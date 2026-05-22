import { DynamicModule, Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { AnalyticsController } from './analytics.controller';
import { AnalyticsService } from './analytics.service';
import { AnalyticsClusters } from '../entities/analytics-clusters.entity';
import { AnalyticsGoldGrowthDynamics } from '../entities/analytics-gold-growth-dynamics.entity';
import { AnalyticsGoldFiscalMonetary } from '../entities/analytics-gold-fiscal-monetary.entity';
import { AnalyticsGoldCrisisRisk } from '../entities/analytics-gold-crisis-risk.entity';
import { GoldGrowthDynamics } from '../entities/gold-growth-dynamics.entity';
import { BigQueryModule } from '../bigquery/bigquery.module';

function createAnalyticsTypeOrmFeatureModule(): DynamicModule | undefined {
  if (process.env.BACKEND_DATA_SOURCE === 'bigquery') {
    return undefined;
  }

  return TypeOrmModule.forFeature([
    AnalyticsClusters,
    AnalyticsGoldGrowthDynamics,
    AnalyticsGoldFiscalMonetary,
    AnalyticsGoldCrisisRisk,
    GoldGrowthDynamics,
  ]);
}

const analyticsTypeOrmFeatureModule = createAnalyticsTypeOrmFeatureModule();

@Module({
  imports: [
    BigQueryModule,
    ...(analyticsTypeOrmFeatureModule ? [analyticsTypeOrmFeatureModule] : []),
  ],
  controllers: [AnalyticsController],
  providers: [AnalyticsService],
})
export class AnalyticsModule {}
