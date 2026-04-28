import { useQuery } from '@tanstack/react-query';
import { analyticsApi } from '@/lib/api/endpoints';

export const useAnomalies = (params?: { country?: string; indicator?: string; threshold?: number; limit?: number }) => {
  return useQuery({
    queryKey: ['anomalies', params],
    queryFn: async () => {
      const { data } = await analyticsApi.getAnomalies(params);
      return data;
    },
  });
};