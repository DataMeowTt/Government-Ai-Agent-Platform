import { DynamicModule, Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { CompareController } from './compare.controller';
import { CompareService } from './compare.service';
import { BigQueryModule } from '../bigquery/bigquery.module';
import { GoldGrowthDynamics } from '../entities/gold-growth-dynamics.entity';

function createCompareTypeOrmFeatureModule(): DynamicModule | undefined {
  if (process.env.BACKEND_DATA_SOURCE === 'bigquery') {
    return undefined;
  }

  return TypeOrmModule.forFeature([GoldGrowthDynamics]);
}

const compareTypeOrmFeatureModule = createCompareTypeOrmFeatureModule();

@Module({
  imports: [
    BigQueryModule,
    ...(compareTypeOrmFeatureModule ? [compareTypeOrmFeatureModule] : []),
  ],
  controllers: [CompareController],
  providers: [CompareService],
})
export class CompareModule {}
