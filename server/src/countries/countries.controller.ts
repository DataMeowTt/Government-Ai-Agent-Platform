import { Controller, Get } from '@nestjs/common';
import { CountriesService } from './countries.service';

@Controller('api/v1/countries')
export class CountriesController {
  constructor(private readonly countriesService: CountriesService) {}

  @Get()
  async getCountries() {
    return this.countriesService.findAll();
  }
}