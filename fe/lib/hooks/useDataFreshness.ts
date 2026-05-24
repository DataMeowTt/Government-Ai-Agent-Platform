import { useQuery } from '@tanstack/react-query';
import { systemApi } from '@/lib/api/endpoints';
import { dataFreshnessResponseSchema } from '@/lib/schemas';
import { DataFreshnessResponse } from '@/lib/types';

const unavailableFreshness: DataFreshnessResponse = {
  available: false,
  last_successful_run_id: null,
  last_successful_sync_at: null,
  latest_data_year: null,
  sources: [],
  status: 'unavailable',
};

export const useDataFreshness = () => {
  return useQuery<DataFreshnessResponse>({
    queryKey: ['dataFreshness'],
    queryFn: async () => {
      const { data } = await systemApi.getDataFreshness();
      const parsed = dataFreshnessResponseSchema.safeParse(data);
      if (!parsed.success) {
        return unavailableFreshness;
      }
      return parsed.data;
    },
    staleTime: 5 * 60 * 1000,
  });
};

