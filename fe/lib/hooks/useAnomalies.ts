import { useQuery } from '@tanstack/react-query';
import { analyticsApi } from '@/lib/api/endpoints';
import { parseArray, anomalySchema } from '@/lib/schemas';
import { AnomalyItem } from '@/lib/types';

export const useAnomalies = (params?: { country?: string; indicator?: string; threshold?: number; limit?: number }) => {
  return useQuery<AnomalyItem[]>({
    queryKey: ['anomalies', params],
    queryFn: async () => {
      const { data } = await analyticsApi.getAnomalies(params);
      return parseArray(anomalySchema, data);
    },
  });
};