import { useQuery } from '@tanstack/react-query';
import { indicatorsApi } from '@/lib/api/endpoints';
import { Indicator } from '@/lib/types';
import { indicatorSchema, parseArray } from '@/lib/schemas';

export const useIndicators = () => {
  return useQuery<Indicator[]>({
    queryKey: ['indicators'],
    queryFn: async () => {
      const { data } = await indicatorsApi.getAll();
      const items = parseArray(indicatorSchema, data);
      return items
        .map((item) => ({
          code: item.code,
          name: item.name_vi || item.name || item.code,
          name_vi: item.name_vi ?? null,
          name_en: item.name_en ?? null,
          category: item.category || 'Khác',
          unit: item.unit || '',
          table: item.table ?? null,
          supports_compare: item.supports_compare,
          supports_ranking: item.supports_ranking,
          supports_trend: item.supports_trend,
          supports_anomaly: item.supports_anomaly,
          supports_coverage: item.supports_coverage,
          description_vi: item.description_vi ?? null,
        }))
        .sort((a, b) => a.name.localeCompare(b.name));
    },
    staleTime: 30 * 60 * 1000,
  });
};
