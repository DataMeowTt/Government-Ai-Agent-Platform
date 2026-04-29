import { useQuery } from '@tanstack/react-query';
import { analyticsApi } from '@/lib/api/endpoints';
import { ClusterItem } from '@/lib/types';
import { parseArray, clusterSchema } from '@/lib/schemas';

export const useClusters = (year: number) => {
  return useQuery<ClusterItem[]>({
    queryKey: ['clusters', year],
    queryFn: async () => {
      const { data } = await analyticsApi.getClusters(year);
      return parseArray(clusterSchema, data);
    },
    enabled: !!year,
    staleTime: 10 * 60 * 1000,
  });
};