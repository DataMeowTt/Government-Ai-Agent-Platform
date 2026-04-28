import { useQuery } from '@tanstack/react-query';
import { analyticsApi } from '@/lib/api/endpoints';

export const useClusters = (year: number) => {
  return useQuery({
    queryKey: ['clusters', year],
    queryFn: async () => {
      const { data } = await analyticsApi.getClusters(year);
      return data;
    },
    enabled: !!year,
  });
};