import { useQueries } from '@tanstack/react-query';
import { countriesApi } from '@/lib/api/endpoints';
import { CompareGroupedData } from '@/lib/types';

const INDICATOR_KEY_MAP: Record<string, string> = {
  rGDP_growth_YoY: 'actual_growth',
  govdebt_GDP: 'actual_debt',
  REER_deviation: 'actual_reer_deviation',
  inflation_cpi: 'actual_inflation',
  poverty_headcount: 'actual_poverty',
  unemployment_total: 'actual_unemployment',
  manuf_va_share: 'actual_manuf_share',
  agri_va_share: 'actual_agri_share',
};

export const useCompare = (countryCodes: string[], indicator: string) => {
  const actualKey = INDICATOR_KEY_MAP[indicator] ?? 'actual_growth';

  const results = useQueries({
    queries: countryCodes.map(code => ({
      queryKey: ['compare', code, indicator],
      queryFn: async () => {
        const { data } = await countriesApi.getFullAnalytics(code);
        return (data as any[]).map((item: any) => ({
          year: item.year,
          value: item[actualKey] ?? null,
          country_code: code,
        }));
      },
      enabled: countryCodes.length > 0,
    })),
  });

  const isLoading = results.some(r => r.isLoading);
  const error = results.find(r => r.error)?.error;
  const flatData = results
    .map(r => r.data ?? [])
    .flat()
    .filter(Boolean) as { year: number; value: number | null; country_code: string }[];

  const grouped: CompareGroupedData = {};
  flatData.forEach(item => {
    if (!grouped[item.country_code]) {
      grouped[item.country_code] = [];
    }
    grouped[item.country_code].push({ year: item.year, value: item.value });
  });

  return { data: grouped, isLoading, error };
};