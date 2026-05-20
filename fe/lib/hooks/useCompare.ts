import { useQueries } from '@tanstack/react-query';
import { countriesApi } from '@/lib/api/endpoints';
import { useIndicators } from './useIndicators';
import { analyticsResponseSchema } from './useCountries';
import { CountryAnalyticsRow, CompareGroupedData } from '@/lib/types';
import { countryAnalyticsRowSchema } from '@/lib/schemas';
import { z } from 'zod';

const INDICATOR_KEY_MAP: Record<string, keyof CountryAnalyticsRow> = {
  rGDP_growth_YoY: 'actual_growth',
  govdebt_GDP: 'actual_debt',
  REER_deviation: 'actual_reer_deviation',
  actual_reer_deviation: 'actual_reer_deviation',
  inflation_cpi: 'actual_inflation',
  poverty_headcount: 'actual_poverty',
  unemployment_total: 'actual_unemployment',
  manuf_va_share: 'actual_manuf_share',
  agri_va_share: 'actual_agri_share',
};

export const useCompare = (countryCodes: string[], indicator: string) => {
  const { data: indicators } = useIndicators();
  const actualKey = INDICATOR_KEY_MAP[indicator];
  const unsupportedIndicator = !actualKey;

  const results = useQueries({
    queries: countryCodes.map((code) => ({
      queryKey: ['compare', code, indicator],
      queryFn: async () => {
        const { data } = await countriesApi.getFullAnalytics(code);
        const parsed = analyticsResponseSchema.safeParse(data);
        const fallback = z.array(countryAnalyticsRowSchema).safeParse(data);
        const rows = parsed.success ? parsed.data.data : fallback.success ? fallback.data : [];
        return rows.map(item => ({
          year: item.year,
          value: (item[actualKey as keyof CountryAnalyticsRow] as number | null | undefined) ?? null,
          country_code: code,
        }));
      },
      enabled: countryCodes.length > 0 && !unsupportedIndicator,
      staleTime: 10 * 60 * 1000,
    })),
  });

  const isLoading = unsupportedIndicator ? false : results.some(r => r.isLoading);
  const error = unsupportedIndicator ? undefined : results.find(r => r.error)?.error;
  const flatData = unsupportedIndicator ? [] : results
    .map(r => r.data ?? [])
    .flat() as { year: number; value: number | null; country_code: string }[];

  const grouped: CompareGroupedData = {};
  flatData.forEach(item => {
    if (!grouped[item.country_code]) grouped[item.country_code] = [];
    grouped[item.country_code].push({ year: item.year, value: item.value });
  });

  const meta = indicators?.find(i => i.code === indicator);

  Object.keys(grouped).forEach((code) => {
    grouped[code] = grouped[code].slice().sort((a, b) => a.year - b.year);
  });

  return {
    data: grouped,
    isLoading,
    error,
    indicatorName: meta?.name || indicator,
    indicatorUnit: meta?.unit || '',
    unsupportedIndicator,
    requestedIndicator: indicator,
    resolvedColumn: actualKey,
  };
};
