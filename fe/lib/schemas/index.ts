import { z } from 'zod';

export const countrySchema = z.object({
  country_code: z.string(),
  country_name: z.string().optional(),
  country: z.string().optional(),
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
  country: z.string().nullable().optional(),
  cluster_id: z.number(),
  latest_valid_year: z.number().optional(),
});

export const indicatorSchema = z.object({
  code: z.string(),
  name: z.string().optional(),
  name_vi: z.string().nullable().optional(),
  name_en: z.string().nullable().optional(),
  category: z.string().optional(),
  unit: z.string().optional(),
  table: z.string().nullable().optional(),
  supports_compare: z.boolean().optional(),
  supports_ranking: z.boolean().optional(),
  supports_trend: z.boolean().optional(),
  supports_anomaly: z.boolean().optional(),
  supports_coverage: z.boolean().optional(),
  description_vi: z.string().nullable().optional(),
});

export const parseArray = <T>(schema: z.ZodType<T>, data: unknown): T[] => {
  if (!Array.isArray(data)) throw new Error('Dữ liệu trả về không đúng định dạng danh sách.');
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

export const countryAnalyticsMetaSchema = z.object({
  country_code: z.string(),
  data_completeness: z.number().nullable().optional(),
  flag_score: z.number().nullable().optional(),
  latest_year: z.number().nullable().optional(),
});
