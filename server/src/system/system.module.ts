import { Module } from '@nestjs/common';
import { BigQueryModule } from '../bigquery/bigquery.module';
import { SystemController } from './system.controller';
import { SystemService } from './system.service';

@Module({
  imports: [BigQueryModule],
  controllers: [SystemController],
  providers: [SystemService],
})
export class SystemModule {}

