import { useQuery } from '@tanstack/react-query';
import { analyticsApi } from '@/lib/api/endpoints';
import { ClusterItem } from '@/lib/types';
import { clusterSchema } from '@/lib/schemas';
import { z } from 'zod';

const clusterArraySchema = z.array(clusterSchema);
const wrappedClustersSchema = z.object({
  items: clusterArraySchema.optional(),
  data: clusterArraySchema.optional(),
});

const normalizeClusters = (raw: unknown): ClusterItem[] => {
  const direct = clusterArraySchema.safeParse(raw);
  if (direct.success) return direct.data;

  const wrapped = wrappedClustersSchema.safeParse(raw);
  if (wrapped.success) {
    return wrapped.data.items || wrapped.data.data || [];
  }

  return [];
};

export const useClusters = (year: number) => {
  return useQuery<ClusterItem[]>({
    queryKey: ['clusters', year],
    queryFn: async () => {
      const { data } = await analyticsApi.getClusters(year);
      return normalizeClusters(data).sort((a, b) => a.cluster_id - b.cluster_id);
    },
    enabled: !!year,
    staleTime: 10 * 60 * 1000,
  });
};
