import { BadRequestException } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { BigQueryCacheService } from './bigquery-cache.service';
import { BigQueryService } from './bigquery.service';

describe('BigQueryService', () => {
  let service: BigQueryService;
  let mockQuery: jest.Mock;

  beforeEach(() => {
    const configService = {
      get: jest.fn((key: string) => {
        if (key === 'BIGQUERY_PROJECT_ID') return 'test-project';
        if (key === 'BIGQUERY_GOLD_DATASET') return 'gov_ai_gold';
        if (key === 'BIGQUERY_ANALYTICS_DATASET') return 'gov_ai_analytics';
        return undefined;
      }),
    } as unknown as ConfigService;
    const cacheService = new BigQueryCacheService();
    service = new BigQueryService(configService, cacheService);
    mockQuery = jest.fn();
    (service as any).client = { query: mockQuery };
  });

  it('normalizes completeness ratio 0.5 to 50 percent without rounding to 1%', async () => {
    mockQuery.mockResolvedValue([
      [
        {
          country_code: 'VNM',
          year: 2020,
          actual_growth: 1.1,
          completeness_score: 0.5,
          flag_score: 0,
        },
      ],
    ]);

    const result = await service.getFullCountryAnalytics('VNM');
    expect(result.meta.data_completeness_ratio).toBeCloseTo(0.5, 4);
    expect(result.meta.data_completeness_percent).toBe(50);
    expect(result.meta.data_completeness).toBe(50);
  });

  it('does not produce NaN when completeness is missing/null', async () => {
    mockQuery.mockResolvedValue([
      [
        {
          country_code: 'VNM',
          year: 2021,
          actual_growth: 1.2,
          completeness_score: null,
          flag_score: 0,
        },
      ],
    ]);

    const result = await service.getFullCountryAnalytics('VNM');
    expect(result.meta.data_completeness_percent).toBe(0);
    expect(Number.isNaN(result.meta.data_completeness)).toBe(false);
  });

  it('rejects unsupported compare indicator and does not fallback', async () => {
    await expect(
      service.getCompareRows({
        countries: ['VNM', 'THA'],
        indicator: 'actual_growth',
      }),
    ).rejects.toBeInstanceOf(BadRequestException);
  });

  it('accepts legacy anomaly alias govdebt and returns canonical indicator', async () => {
    mockQuery.mockResolvedValue([
      [
        {
          country_code: 'VNM',
          year: 2022,
          indicator: 'govdebt_GDP',
          actual_value: 58.5,
          anomaly_score: 0.88,
          country_name: 'Vietnam',
          total_count: 1,
        },
      ],
    ]);

    const result = await service.getAnomalies({
      countryCode: 'VNM',
      indicator: 'govdebt',
      threshold: 0.75,
      limit: 15,
      offset: 0,
    });

    expect(result.items).toHaveLength(1);
    expect(result.items[0].indicator).toBe('govdebt_GDP');
  });

  it('returns trend_value in compare rows when available', async () => {
    mockQuery.mockResolvedValue([
      [
        {
          country_code: 'VNM',
          country: 'Vietnam',
          year: 2020,
          indicator: 'govdebt_GDP',
          indicator_name: 'Nợ công/GDP',
          category: 'fiscal_monetary',
          unit: '%',
          value: 55.2,
          trend_value: 53.9,
        },
      ],
    ]);

    const rows = await service.getCompareRows({
      countries: ['VNM'],
      indicator: 'govdebt_GDP',
      from: 2010,
      to: 2023,
    });

    expect(rows).toHaveLength(1);
    expect(rows[0].trend_value).toBe(53.9);
  });

  it('country indicators query excludes technical columns', async () => {
    mockQuery.mockResolvedValue([[]]);

    await service.getCountryIndicators('VNM');

    const queryTexts = mockQuery.mock.calls.map(call => String(call[0].query));
    queryTexts.forEach(query => {
      expect(query).not.toMatch(/completeness_score/i);
      expect(query).not.toMatch(/flag_score/i);
      expect(query).not.toMatch(/\bdecade\b/i);
    });
  });

  it('returns normalized successful data freshness response', async () => {
    mockQuery.mockResolvedValue([
      [
        {
          run_id: 'run-current-success',
          published_at: '2026-05-24T02:00:00Z',
          latest_data_year: 2025,
          sources_json:
            '[{"name":"wdi","version":null,"updated_at":null}]',
        },
      ],
    ]);

    const result = await service.getDataFreshness();

    expect(result).toEqual({
      available: true,
      last_successful_run_id: 'run-current-success',
      last_successful_sync_at: '2026-05-24T02:00:00Z',
      latest_data_year: 2025,
      sources: [{ name: 'wdi', version: null, updated_at: null }],
      status: 'success',
    });
  });

  it('returns unavailable freshness response when no successful row is found', async () => {
    mockQuery.mockResolvedValue([[]]);

    await expect(service.getDataFreshness()).resolves.toEqual({
      available: false,
      last_successful_run_id: null,
      last_successful_sync_at: null,
      latest_data_year: null,
      sources: [],
      status: 'unavailable',
    });
  });

  it('uses success-only predicates and selected columns for freshness query', async () => {
    mockQuery.mockResolvedValue([[]]);

    await service.getDataFreshness();
    const queryText = String(mockQuery.mock.calls[0][0].query);

    expect(queryText).toContain('SELECT');
    expect(queryText).toContain('run_id');
    expect(queryText).toContain('published_at');
    expect(queryText).toContain('latest_data_year');
    expect(queryText).toContain('sources_json');
    expect(queryText).not.toMatch(/\bSELECT\s+\*/i);
    expect(queryText).toContain("status = 'SUCCESS'");
    expect(queryText).toContain('warehouse_publish_performed = TRUE');
    expect(queryText).toContain('publish_performed = TRUE');
    expect(queryText).toContain('last_successful_updated = TRUE');
    expect(queryText).toContain('published_at IS NOT NULL');
    expect(queryText).toContain('ORDER BY published_at DESC');
    expect(queryText).toContain('LIMIT 1');
  });

  it('maps public latest-success identifier from run_id, not persisted last_successful_run_id', async () => {
    mockQuery.mockResolvedValue([
      [
        {
          run_id: 'run-current-success',
          last_successful_run_id: 'run-previous-success',
          published_at: '2026-05-24T02:00:00Z',
          latest_data_year: 2025,
          sources_json:
            '[{"name":"wdi","version":null,"updated_at":null}]',
        },
      ],
    ]);

    const result = await service.getDataFreshness();
    const queryText = String(mockQuery.mock.calls[0][0].query);

    expect(result.last_successful_run_id).toBe('run-current-success');
    expect(result.last_successful_run_id).not.toBe('run-previous-success');
    expect(queryText).toContain('run_id');
    expect(queryText).not.toContain('last_successful_run_id');
  });

  it('returns empty sources when sources_json is malformed', async () => {
    mockQuery.mockResolvedValue([
      [
        {
          run_id: 'run-current-success',
          published_at: '2026-05-24T02:00:00Z',
          latest_data_year: 2025,
          sources_json: '{invalid-json}',
        },
      ],
    ]);

    const result = await service.getDataFreshness();
    expect(result.sources).toEqual([]);
    expect(result.status).toBe('success');
  });
});
