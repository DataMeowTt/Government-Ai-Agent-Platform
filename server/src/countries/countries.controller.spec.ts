import { Test, TestingModule } from '@nestjs/testing';
import { CountriesController } from './countries.controller';
import { CountriesService } from './countries.service';

describe('CountriesController', () => {
  let controller: CountriesController;
  const countriesService = {
    findAll: jest.fn(),
    getFullCountryAnalytics: jest.fn(),
    getClusterBenchmark: jest.fn(),
    triggerAnalyticsWorker: jest.fn(),
    getCountryAnomalies: jest.fn(),
  };

  beforeEach(async () => {
    jest.clearAllMocks();
    const module: TestingModule = await Test.createTestingModule({
      controllers: [CountriesController],
      providers: [
        {
          provide: CountriesService,
          useValue: countriesService,
        },
      ],
    }).compile();

    controller = module.get<CountriesController>(CountriesController);
  });

  it('should be defined', () => {
    expect(controller).toBeDefined();
  });

  it('normalizes country code on full analytics endpoint', async () => {
    countriesService.getFullCountryAnalytics.mockResolvedValueOnce({ meta: {}, data: [] });
    await controller.getFullAnalytics('vnm');
    expect(countriesService.getFullCountryAnalytics).toHaveBeenCalledWith('VNM');
  });
});
