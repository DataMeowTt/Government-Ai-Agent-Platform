import { useQuery } from '@tanstack/react-query';
import { countriesApi } from '@/lib/api/endpoints';
import { parseArray, countrySchema, countryAnalyticsRowSchema } from '@/lib/schemas';
import { Country } from '@/lib/types';
import { z } from 'zod';

export const analyticsResponseSchema = z.object({
  meta: z.object({ country_code: z.string(), data_completeness: z.number(), flag_score: z.number(), latest_year: z.number().nullable() }),
  data: z.array(countryAnalyticsRowSchema),
});

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
  return useQuery({
    queryKey: ['countryAnalytics', code],
    queryFn: async () => {
      const { data } = await countriesApi.getFullAnalytics(code);
      return analyticsResponseSchema.parse(data);
    },
    enabled: !!code,
    select: (res) => ({ data: res.data, meta: res.meta }),
  });
};

export const useClusterBenchmark = (code: string, indicator: string, year: number | undefined) => {
  return useQuery({
    queryKey: ['clusterBenchmark', code, indicator, year],
    queryFn: async () => {
      if (!year) return null;
      const { data } = await countriesApi.getClusterBenchmark(code, indicator, year);
      return data;
    },
    enabled: !!code && !!indicator && !!year,
    staleTime: 5 * 60 * 1000,
  });
};
