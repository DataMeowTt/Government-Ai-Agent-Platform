import { Controller, Get, Query } from '@nestjs/common';
import { IndicatorsService } from './indicators.service';

@Controller('api/v1/indicators')
export class IndicatorsController {
  constructor(private readonly indicatorsService: IndicatorsService) {}

  @Get()
  getIndicators(@Query('category') category?: string) {
    if (category) {
      return this.indicatorsService.findByCategory(category);
    }
    return this.indicatorsService.findAll();
  }
}