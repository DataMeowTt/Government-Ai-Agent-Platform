import { z } from 'zod';

export const countrySchema = z.object({
  country_code: z.string(),
  country_name: z.string(),
  region: z.string().nullable().optional(),
});

export const anomalySchema = z.object({
  country_code: z.string(),
  country_name: z.string(),
  year: z.number(),
  indicator: z.string(),
  actual_value: z.number().nullable(),
  anomaly_score: z.number().nullable(),
});

export const clusterSchema = z.object({
  year: z.number(),
  country_code: z.string(),
  country: z.string().optional(),
  cluster_id: z.number(),
  latest_valid_year: z.number().optional(),
});

export const indicatorSchema = z.object({
  code: z.string(),
  name: z.string(),
  category: z.string(),
  unit: z.string(),
  table: z.string(),
});

export const parseArray = <T>(schema: z.ZodType<T>, data: unknown): T[] => {
  if (!Array.isArray(data)) throw new Error('API response is not an array');
  return data.map((item) => schema.parse(item));
};

export const countryAnalyticsRowSchema = z.object({
  country_code: z.string(),
  year: z.number(),
  actual_growth: z.number().nullable().optional(),
  trend_growth: z.number().nullable().optional(),
  anomaly_growth: z.number().nullable().optional(),
  actual_debt: z.number().nullable().optional(),
  anomaly_debt: z.number().nullable().optional(),
  actual_inflation: z.number().nullable().optional(),
  actual_poverty: z.number().nullable().optional(),
  actual_unemployment: z.number().nullable().optional(),
  actual_manuf_share: z.number().nullable().optional(),
  actual_agri_share: z.number().nullable().optional(),
  actual_reer_deviation: z.number().nullable().optional(),
  anomaly_reer_deviation: z.number().nullable().optional(),
  cluster_id: z.number().nullable().optional(),
});
