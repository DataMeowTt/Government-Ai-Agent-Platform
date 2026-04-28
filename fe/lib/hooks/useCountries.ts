import { useQuery } from '@tanstack/react-query';
import { countriesApi } from '@/lib/api/endpoints';

export const useCountries = () => {
  return useQuery({
    queryKey: ['countries'],
    queryFn: async () => {
      const { data } = await countriesApi.getAll();
      return data;
    },
    staleTime: 5 * 60 * 1000,
  });
};