import { Controller, Get } from '@nestjs/common';
import { DataFreshnessResponse } from '../bigquery/bigquery.types';
import { SystemService } from './system.service';

@Controller('api/v1/system')
export class SystemController {
  constructor(private readonly systemService: SystemService) {}

  @Get('data-freshness')
  async getDataFreshness(): Promise<DataFreshnessResponse> {
    return this.systemService.getDataFreshness();
  }
}

