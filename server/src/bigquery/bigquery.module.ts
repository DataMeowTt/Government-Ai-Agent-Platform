import { Module } from '@nestjs/common';
import { BigQueryService } from './bigquery.service';
import { BigQueryCacheService } from './bigquery-cache.service';

@Module({
  providers: [BigQueryService, BigQueryCacheService],
  exports: [BigQueryService],
})
export class BigQueryModule {}

