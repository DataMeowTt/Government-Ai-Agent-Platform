import { useQuery } from '@tanstack/react-query';
import { countriesApi } from '@/lib/api/endpoints';
import {
  countryAnalyticsMetaSchema,
  countryAnalyticsRowSchema,
  countryIndicatorsResponseSchema,
  countrySchema,
  parseArray,
} from '@/lib/schemas';
import {
  ClusterBenchmark,
  Country,
  CountryAnalyticsResponse,
  CountryAnalyticsRow,
  CountryIndicatorsResponse,
} from '@/lib/types';
import { z } from 'zod';

export const analyticsResponseSchema = z.object({
  meta: countryAnalyticsMetaSchema,
  data: z.array(countryAnalyticsRowSchema),
});

const analyticsRowsOnlySchema = z.array(countryAnalyticsRowSchema);

const clusterBenchmarkSchema: z.ZodType<ClusterBenchmark> = z.object({
  cluster_id: z.number(),
  indicator: z.string(),
  year: z.number(),
  average: z.number(),
  members: z.array(
    z.object({
      country_code: z.string(),
      country_name: z.string().nullable().optional(),
      year: z.number().nullable().optional(),
      value: z.number().nullable(),
    })
  ),
});

const normalizeCountry = (input: unknown): Country | null => {
  const parsed = countrySchema.safeParse(input);
  if (!parsed.success) return null;
  const country_name = parsed.data.country_name || parsed.data.country || '';
  if (!parsed.data.country_code || !country_name) return null;
  return {
    country_code: parsed.data.country_code,
    country_name,
    country: parsed.data.country ?? null,
    region: parsed.data.region ?? null,
  };
};

const dedupeCountries = (items: unknown[]): Country[] => {
  const map = new Map<string, Country>();
  items.forEach((item) => {
    const normalized = normalizeCountry(item);
    if (!normalized) return;
    if (!map.has(normalized.country_code)) {
      map.set(normalized.country_code, normalized);
      return;
    }
    const current = map.get(normalized.country_code)!;
    if ((!current.region || current.region === 'N/A') && normalized.region) {
      map.set(normalized.country_code, normalized);
    }
  });
  return Array.from(map.values()).sort((a, b) => a.country_name.localeCompare(b.country_name));
};

const normalizeAnalyticsPayload = (code: string, raw: unknown): CountryAnalyticsResponse => {
  const wrapped = analyticsResponseSchema.safeParse(raw);
  if (wrapped.success) {
    return {
      meta: wrapped.data.meta,
      data: wrapped.data.data.slice().sort((a, b) => a.year - b.year),
    };
  }

  const rows = analyticsRowsOnlySchema.parse(raw);
  return {
    meta: {
      country_code: code,
      data_completeness: null,
      flag_score: null,
      latest_year: rows.length ? rows[rows.length - 1].year : null,
    },
    data: rows.slice().sort((a, b) => a.year - b.year),
  };
};

const normalizeCountryIndicatorsPayload = (
  code: string,
  raw: unknown,
): CountryIndicatorsResponse => {
  const parsed = countryIndicatorsResponseSchema.safeParse(raw);
  if (parsed.success) {
    return {
      country_code: parsed.data.country_code,
      rows: parsed.data.rows.slice().sort((a, b) => {
        if (a.indicator !== b.indicator) return a.indicator.localeCompare(b.indicator);
        return a.year - b.year;
      }),
      summary: (parsed.data.summary || []).slice().sort((a, b) =>
        a.indicator.localeCompare(b.indicator),
      ),
    };
  }

  return {
    country_code: code,
    rows: [],
    summary: [],
  };
};

export const useCountries = () => {
  return useQuery<Country[]>({
    queryKey: ['countries'],
    queryFn: async () => {
      const { data } = await countriesApi.getAll();
      const raw = parseArray(z.unknown(), data);
      return dedupeCountries(raw);
    },
    staleTime: 10 * 60 * 1000,
  });
};

export const useCountryAnalytics = (code: string) => {
  return useQuery<CountryAnalyticsResponse>({
    queryKey: ['countryAnalytics', code],
    queryFn: async () => {
      const { data } = await countriesApi.getFullAnalytics(code);
      return normalizeAnalyticsPayload(code, data);
    },
    enabled: !!code,
    select: (res) => ({
      data: res.data.slice().sort((a: CountryAnalyticsRow, b: CountryAnalyticsRow) => a.year - b.year),
      meta: res.meta,
    }),
    staleTime: 5 * 60 * 1000,
  });
};

export const useClusterBenchmark = (code: string, indicator: string, year: number | undefined) => {
  return useQuery<ClusterBenchmark | null>({
    queryKey: ['clusterBenchmark', code, indicator, year],
    queryFn: async () => {
      if (!year) return null;
      const { data } = await countriesApi.getClusterBenchmark(code, indicator, year);
      const parsed = clusterBenchmarkSchema.safeParse(data);
      if (!parsed.success) return null;
      return parsed.data;
    },
    enabled: !!code && !!indicator && !!year,
    staleTime: 5 * 60 * 1000,
  });
};

export const useCountryIndicators = (code: string) => {
  return useQuery<CountryIndicatorsResponse>({
    queryKey: ['countryIndicators', code],
    queryFn: async () => {
      const { data } = await countriesApi.getIndicators(code);
      return normalizeCountryIndicatorsPayload(code, data);
    },
    enabled: !!code,
    staleTime: 5 * 60 * 1000,
  });
};
