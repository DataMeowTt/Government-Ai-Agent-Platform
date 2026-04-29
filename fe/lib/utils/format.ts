export const formatNumber = (value: number | null | undefined, decimals = 2): string => {
  if (value === null || value === undefined) return 'N/A';
  return value.toFixed(decimals);
};

export const getAnomalyColor = (score: number | null | undefined): string => {
  if (score == null) return 'bg-gray-100 text-gray-600';
  if (score >= 0.9) return 'bg-red-100 text-red-700 border border-red-200';
  if (score >= 0.75) return 'bg-orange-100 text-orange-700 border border-orange-200';
  return 'bg-green-100 text-green-700 border border-green-200';
};