import { useQuery } from '@tanstack/react-query';
import { countriesApi } from '@/lib/api/endpoints';
import { parseArray, countrySchema, countryAnalyticsRowSchema } from '@/lib/schemas';
import { Country, CountryAnalyticsRow } from '@/lib/types';

export const useCountries = () => {
  return useQuery<Country[]>({
    queryKey: ['countries'],
    queryFn: async () => {
      const { data } = await countriesApi.getAll();
      return parseArray(countrySchema, data);
    },
    staleTime: 10 * 60 * 1000,
  });
};

export const useCountryAnalytics = (code: string) => {
  return useQuery<CountryAnalyticsRow[]>({
    queryKey: ['countryAnalytics', code],
    queryFn: async () => {
      const { data } = await countriesApi.getFullAnalytics(code);
      return parseArray(countryAnalyticsRowSchema, data);
    },
    enabled: !!code,
  });
};