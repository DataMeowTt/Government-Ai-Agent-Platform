import { useQueries } from '@tanstack/react-query';
import { countriesApi } from '@/lib/api/endpoints';

export const useCompare = (countryCodes: string[], indicator: string) => {
  const results = useQueries({
    queries: countryCodes.map(code => ({
      queryKey: ['compare', code, indicator],
      queryFn: async () => {
        const { data } = await countriesApi.getFullAnalytics(code);
        let actualKey = '';
        if (indicator === 'rGDP_growth_YoY') actualKey = 'actual_growth';
        else if (indicator === 'govdebt_GDP') actualKey = 'actual_debt';
        else if (indicator === 'REER_deviation') actualKey = 'actual_reer_deviation';
        else if (indicator === 'inflation_cpi') actualKey = 'actual_inflation';
        else if (indicator === 'poverty_headcount') actualKey = 'actual_poverty';
        else if (indicator === 'unemployment_total') actualKey = 'actual_unemployment';
        else if (indicator === 'manuf_va_share') actualKey = 'actual_manuf_share';
        else if (indicator === 'agri_va_share') actualKey = 'actual_agri_share';
        else actualKey = 'actual_growth';

        return data.map((item: any) => ({
          year: item.year,
          value: item[actualKey],
          country_code: code,
        }));
      },
      enabled: countryCodes.length > 0,
    })),
  });

  const isLoading = results.some(r => r.isLoading);
  const error = results.find(r => r.error)?.error;
  const data = results.map(r => r.data).flat().filter(Boolean);

  const grouped: Record<string, any[]> = {};
  data.forEach(item => {
    if (!grouped[item.country_code]) grouped[item.country_code] = [];
    grouped[item.country_code].push({ year: item.year, value: item.value });
  });

  return { data: grouped, isLoading, error };
};