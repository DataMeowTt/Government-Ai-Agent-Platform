import { useQuery } from '@tanstack/react-query';
import { indicatorsApi } from '@/lib/api/endpoints';
import { Indicator } from '@/lib/types';
import { parseArray, indicatorSchema } from '@/lib/schemas';

export const useIndicators = () => {
  return useQuery<Indicator[]>({
    queryKey: ['indicators'],
    queryFn: async () => {
      const { data } = await indicatorsApi.getAll();
      return parseArray(indicatorSchema, data);
    },
    staleTime: 30 * 60 * 1000,
  });
};