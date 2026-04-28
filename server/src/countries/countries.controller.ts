import { Controller, Get, Param } from '@nestjs/common';
import { CountriesService } from './countries.service';

@Controller('api/v1/countries')
export class CountriesController {
  constructor(private readonly countriesService: CountriesService) { }


  @Get(':code/full-analytics')
  async getFullAnalytics(@Param('code') code: string) {
    return this.countriesService.getFullCountryAnalytics(code.toUpperCase());
  }
}