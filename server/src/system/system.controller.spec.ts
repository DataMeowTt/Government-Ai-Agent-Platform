import { Test, TestingModule } from '@nestjs/testing';
import { SystemController } from './system.controller';
import { SystemService } from './system.service';

describe('SystemController', () => {
  let controller: SystemController;
  const systemService = {
    getDataFreshness: jest.fn(),
  };

  beforeEach(async () => {
    jest.clearAllMocks();
    const module: TestingModule = await Test.createTestingModule({
      controllers: [SystemController],
      providers: [
        {
          provide: SystemService,
          useValue: systemService,
        },
      ],
    }).compile();

    controller = module.get<SystemController>(SystemController);
  });

  it('returns the data freshness payload', async () => {
    const payload = {
      available: true,
      last_successful_run_id: 'run-current-success',
      last_successful_sync_at: '2026-05-24T02:00:00Z',
      latest_data_year: 2025,
      sources: [{ name: 'wdi', version: null, updated_at: null }],
      status: 'success' as const,
    };
    systemService.getDataFreshness.mockResolvedValueOnce(payload);

    await expect(controller.getDataFreshness()).resolves.toEqual(payload);
    expect(systemService.getDataFreshness).toHaveBeenCalledTimes(1);
  });
});

