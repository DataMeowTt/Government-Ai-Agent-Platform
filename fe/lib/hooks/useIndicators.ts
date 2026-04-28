import { useQuery } from '@tanstack/react-query';
import { indicatorsApi } from '@/lib/api/endpoints';

export const useIndicators = () => {
  return useQuery({
    queryKey: ['indicators'],
    queryFn: async () => {
      const { data } = await indicatorsApi.getAll();
      return data;
    },
  });
};