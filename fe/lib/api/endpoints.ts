import apiClient from './client';

export const countriesApi = {
  getAll: () => apiClient.get('/api/v1/countries'),
  getFullAnalytics: (code: string) => apiClient.get(`/api/v1/countries/${code}/full-analytics`),
};

export const indicatorsApi = {
  getAll: () => apiClient.get('/api/v1/indicators'),
  getByCategory: (category: string) => apiClient.get(`/api/v1/indicators?category=${category}`),
};

export const analyticsApi = {
  getClusters: (year: number) => apiClient.get(`/api/v1/analytics/clusters?year=${year}`),
  getAnomalies: (params?: { 
    country?: string; 
    indicator?: string; 
    threshold?: number; 
    limit?: number;
    offset?: number;
  }) =>
    apiClient.get('/api/v1/analytics/anomalies', { params }),
};