import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { GoldGrowthDynamics } from '../entities/gold-growth-dynamics.entity';

@Injectable()
export class CountriesService {
  constructor(
    @InjectRepository(GoldGrowthDynamics)
    private growthRepo: Repository<GoldGrowthDynamics>,
  ) {}

  async findAll() {
    const results = await this.growthRepo
      .createQueryBuilder('g')
      .select([
        'g.country_code as country_code',
        'g.country as country_name',
      ])
      .distinct(true)
      .orderBy('g.country', 'ASC')
      .getRawMany();

    return results;
  }
}