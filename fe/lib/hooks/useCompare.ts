import { useQuery } from '@tanstack/react-query';
import { compareApi } from '@/lib/api/endpoints';
import { useIndicators } from './useIndicators';
import { CompareGroupedData } from '@/lib/types';
import { compareRowSchema } from '@/lib/schemas';
import { parseArray } from '@/lib/schemas';

export const useCompare = (
  countryCodes: string[],
  indicator: string,
  from?: number,
  to?: number,
) => {
  const { data: indicators } = useIndicators();
  const compareQuery = useQuery({
    queryKey: ['compare', countryCodes.join(','), indicator, from, to],
    queryFn: async () => {
      const { data } = await compareApi.getRows({
        countries: countryCodes,
        indicator,
        from,
        to,
      });
      return parseArray(compareRowSchema, data);
    },
    enabled: countryCodes.length > 0 && !!indicator,
    staleTime: 5 * 60 * 1000,
  });

  const grouped: CompareGroupedData = {};
  (compareQuery.data || []).forEach(item => {
    if (!grouped[item.country_code]) grouped[item.country_code] = [];
    grouped[item.country_code].push({
      year: item.year,
      value: item.value,
      trend_value: item.trend_value ?? null,
    });
  });

  const meta = indicators?.find(i => i.code === indicator);

  Object.keys(grouped).forEach((code) => {
    grouped[code] = grouped[code].slice().sort((a, b) => a.year - b.year);
  });

  return {
    data: grouped,
    isLoading: compareQuery.isLoading,
    error: compareQuery.error,
    indicatorName: meta?.name || indicator,
    indicatorUnit: meta?.unit || '',
    unsupportedIndicator: false,
    requestedIndicator: indicator,
  };
};
