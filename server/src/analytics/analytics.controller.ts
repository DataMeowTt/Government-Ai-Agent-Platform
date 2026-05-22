import { Controller, Get, Query, DefaultValuePipe, ParseIntPipe, ParseFloatPipe } from '@nestjs/common';
import { AnalyticsService } from './analytics.service';

@Controller('api/v1/analytics')
export class AnalyticsController {
  constructor(private readonly analyticsService: AnalyticsService) {}

  @Get('clusters')
  async getClusters(@Query('year', ParseIntPipe) year: number) {
    return this.analyticsService.getClusters(year);
  }

  @Get('anomalies')
  async getAnomalies(
    @Query('country') country?: string,
    @Query('indicator') indicator?: string,
    @Query('threshold', new DefaultValuePipe(0.75), ParseFloatPipe) threshold?: number,
    @Query('limit', new DefaultValuePipe(15), ParseIntPipe) limit?: number,
    @Query('offset', new DefaultValuePipe(0), ParseIntPipe) offset?: number,
  ) {
    return this.analyticsService.getAnomalies(country, indicator, threshold, limit, offset);
  }
}