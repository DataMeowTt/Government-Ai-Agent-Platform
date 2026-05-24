import apiClient from './client';
import type { AiChatRequest } from '@/lib/types/aiChat';

export const countriesApi = {
  getAll: () => apiClient.get('/api/v1/countries'),
  getFullAnalytics: (code: string) => apiClient.get(`/api/v1/countries/${code}/full-analytics`),
  getIndicators: (code: string) => apiClient.get(`/api/v1/countries/${code}/indicators`),
  getClusterBenchmark: (code: string, indicator: string, year: number) =>
    apiClient.get(`/api/v1/countries/${code}/cluster-benchmark`, { params: { indicator, year } }),
};

export const compareApi = {
  getRows: (params: { countries: string[]; indicator: string; from?: number; to?: number }) =>
    apiClient.get('/api/v1/compare', {
      params: {
        countries: params.countries.join(','),
        indicator: params.indicator,
        from: params.from,
        to: params.to,
      },
    }),
};

export const indicatorsApi = {
  getAll: () => apiClient.get('/api/v1/indicators'),
  getByCategory: (category: string) => apiClient.get('/api/v1/indicators', { params: { category } }),
};

export const analyticsApi = {
  getClusters: (year: number) => apiClient.get('/api/v1/analytics/clusters', { params: { year } }),
  getAnomalies: (params?: { country?: string; indicator?: string; threshold?: number; limit?: number; offset?: number }) =>
    apiClient.get('/api/v1/analytics/anomalies', { params }),
};

export const aiChatApi = {
  sendMessage: (payload: AiChatRequest) =>
    apiClient.post('/api/v1/ai/chat', payload, {
      timeout: 120000,
    }),
  health: () => apiClient.get('/api/v1/ai/health'),
};

export const systemApi = {
  getDataFreshness: () => apiClient.get('/api/v1/system/data-freshness'),
};
