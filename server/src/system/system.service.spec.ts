import { Test, TestingModule } from '@nestjs/testing';
import { BigQueryService } from '../bigquery/bigquery.service';
import { SystemService } from './system.service';

describe('SystemService', () => {
  let service: SystemService;
  const bigQueryService = {
    getDataFreshness: jest.fn(),
  };

  beforeEach(async () => {
    jest.clearAllMocks();
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        SystemService,
        {
          provide: BigQueryService,
          useValue: bigQueryService,
        },
      ],
    }).compile();

    service = module.get<SystemService>(SystemService);
  });

  it('delegates data freshness read to BigQueryService', async () => {
    bigQueryService.getDataFreshness.mockResolvedValueOnce({
      available: false,
      last_successful_run_id: null,
      last_successful_sync_at: null,
      latest_data_year: null,
      sources: [],
      status: 'unavailable',
    });

    const result = await service.getDataFreshness();
    expect(bigQueryService.getDataFreshness).toHaveBeenCalledTimes(1);
    expect(result.status).toBe('unavailable');
  });
});

