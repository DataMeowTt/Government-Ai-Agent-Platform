import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { CountriesController } from './countries.controller';
import { CountriesService } from './countries.service';
import { GoldGrowthDynamics } from '../entities/gold-growth-dynamics.entity';

@Module({
  imports: [TypeOrmModule.forFeature([GoldGrowthDynamics])],
  controllers: [CountriesController],
  providers: [CountriesService],
})
export class CountriesModule {}