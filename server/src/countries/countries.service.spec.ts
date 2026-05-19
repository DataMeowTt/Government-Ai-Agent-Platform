import { Test, TestingModule } from '@nestjs/testing';
import { CountriesService } from './countries.service';
import { ConfigService } from '@nestjs/config';
import { BigQueryService } from '../bigquery/bigquery.service';
import { getRepositoryToken } from '@nestjs/typeorm';
import { GoldGrowthDynamics } from '../entities/gold-growth-dynamics.entity';
import { AnalyticsGoldGrowthDynamics } from '../entities/analytics-gold-growth-dynamics.entity';
import { AnalyticsClusters } from '../entities/analytics-clusters.entity';

describe('CountriesService', () => {
  let service: CountriesService;
  let configService: { get: jest.Mock };
  let bigQueryService: {
    listCountries: jest.Mock;
    getFullCountryAnalytics: jest.Mock;
    getClusterBenchmark: jest.Mock;
  };

  beforeEach(async () => {
    configService = { get: jest.fn() };
    bigQueryService = {
      listCountries: jest.fn(),
      getFullCountryAnalytics: jest.fn(),
      getClusterBenchmark: jest.fn(),
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        CountriesService,
        {
          provide: ConfigService,
          useValue: configService,
        },
        {
          provide: BigQueryService,
          useValue: bigQueryService,
        },
        {
          provide: getRepositoryToken(GoldGrowthDynamics),
          useValue: {},
        },
        {
          provide: getRepositoryToken(AnalyticsGoldGrowthDynamics),
          useValue: {},
        },
        {
          provide: getRepositoryToken(AnalyticsClusters),
          useValue: {},
        },
      ],
    }).compile();

    service = module.get<CountriesService>(CountriesService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  it('findAll delegates to bigquery listCountries in bigquery mode', async () => {
    configService.get.mockImplementation((key: string) =>
      key === 'BACKEND_DATA_SOURCE' ? 'bigquery' : undefined,
    );
    bigQueryService.listCountries.mockResolvedValueOnce([{ country_code: 'VNM' }]);

    const result = await service.findAll();

    expect(bigQueryService.listCountries).toHaveBeenCalledTimes(1);
    expect(result).toEqual([{ country_code: 'VNM' }]);
  });

  it('getFullCountryAnalytics delegates to bigquery in bigquery mode', async () => {
    configService.get.mockImplementation((key: string) =>
      key === 'BACKEND_DATA_SOURCE' ? 'bigquery' : undefined,
    );
    bigQueryService.getFullCountryAnalytics.mockResolvedValueOnce({
      meta: { country_code: 'VNM', data_completeness: 0, flag_score: 0, latest_year: null },
      data: [],
    });

    const result = await service.getFullCountryAnalytics('VNM');

    expect(bigQueryService.getFullCountryAnalytics).toHaveBeenCalledWith('VNM');
    expect(result).toEqual({
      meta: { country_code: 'VNM', data_completeness: 0, flag_score: 0, latest_year: null },
      data: [],
    });
  });

  it('getClusterBenchmark delegates to bigquery in bigquery mode', async () => {
    configService.get.mockImplementation((key: string) =>
      key === 'BACKEND_DATA_SOURCE' ? 'bigquery' : undefined,
    );
    bigQueryService.getClusterBenchmark.mockResolvedValueOnce(null);

    const result = await service.getClusterBenchmark('VNM', 'govdebt_GDP', 2025);

    expect(bigQueryService.getClusterBenchmark).toHaveBeenCalledWith('VNM', 'govdebt_GDP', 2025);
    expect(result).toBeNull();
  });

  it('does not throw repository unavailable in bigquery mode', async () => {
    configService.get.mockImplementation((key: string) =>
      key === 'BACKEND_DATA_SOURCE' ? 'bigquery' : undefined,
    );
    bigQueryService.getFullCountryAnalytics.mockResolvedValueOnce({
      meta: { country_code: 'THA', data_completeness: 0, flag_score: 0, latest_year: null },
      data: [],
    });

    await expect(service.getFullCountryAnalytics('THA')).resolves.toBeDefined();
  });
});
