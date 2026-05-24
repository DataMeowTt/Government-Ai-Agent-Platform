import { Injectable } from '@nestjs/common';
import { BigQueryService } from '../bigquery/bigquery.service';
import { DataFreshnessResponse } from '../bigquery/bigquery.types';

@Injectable()
export class SystemService {
  constructor(private readonly bigQueryService: BigQueryService) {}

  async getDataFreshness(): Promise<DataFreshnessResponse> {
    return this.bigQueryService.getDataFreshness();
  }
}

