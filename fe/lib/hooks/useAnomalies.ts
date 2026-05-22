import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { analyticsApi } from '@/lib/api/endpoints';
import { anomalySchema } from '@/lib/schemas';
import { z } from 'zod';

const anomalyResponseSchema = z.object({
  items: z.array(anomalySchema).optional(),
  meta: z.object({ total_count: z.number().optional(), limit: z.number().optional(), offset: z.number().optional() }).optional(),
});

export const useAnomalies = ({
  country, indicator, threshold = 0.75, limit = 15, offset = 0
}: { country?: string; indicator?: string; threshold?: number; limit?: number; offset?: number } = {}) => {
  const queryResult = useQuery({
    queryKey: ['anomalies', country, indicator, threshold, limit, offset],
    queryFn: async () => {
      const { data } = await analyticsApi.getAnomalies({ country, indicator, threshold, limit, offset });
      const wrapped = anomalyResponseSchema.safeParse(data);
      if (wrapped.success) {
        const sortedItems = (wrapped.data.items || []).slice().sort((a, b) => a.year - b.year);
        return {
          items: sortedItems,
          meta: wrapped.data.meta || {},
        };
      }
      const direct = z.array(anomalySchema).safeParse(data);
      if (direct.success) {
        const sortedItems = direct.data.slice().sort((a, b) => a.year - b.year);
        return {
          items: sortedItems,
          meta: { total_count: sortedItems.length, limit, offset },
        };
      }
      throw new Error('Dữ liệu bất thường không hợp lệ.');
    },
    staleTime: 30 * 1000,
    placeholderData: keepPreviousData,
  });

  const { data, isLoading, isFetching, isError, error } = queryResult;
  return {
    data: data?.items || [],
    total: data?.meta.total_count ?? data?.items?.length ?? 0,
    isLoading,
    isFetching,
    isError,
    error: error as Error | null,
    isEmpty: !isLoading && !isError && (!data || !data.items || data.items.length === 0),
  };
};
