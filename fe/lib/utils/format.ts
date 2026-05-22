const YEAR_FIELD_RE = /(^year$|_year$|year_)/i;

export const formatNullable = (value: unknown, fallback = 'N/A'): string => {
  if (value === null || value === undefined) return fallback;
  if (typeof value === 'number' && Number.isNaN(value)) return fallback;
  return String(value);
};

export const formatYear = (value: number | string | null | undefined): string => {
  if (value === null || value === undefined || value === '') return 'N/A';
  const numeric = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(numeric)) return formatNullable(value);
  return String(Math.trunc(numeric));
};

export const formatNumber = (
  value: number | null | undefined,
  decimals = 2,
  useGrouping = true
): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return 'N/A';
  return value.toLocaleString('vi-VN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
    useGrouping,
  });
};

export const formatPercent = (value: number | null | undefined, decimals = 2): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return 'N/A';
  return `${formatNumber(value, decimals)}%`;
};

export const formatCurrencyCurrentUSD = (
  value: number | null | undefined,
  decimals = 0
): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return 'N/A';
  return `${formatNumber(value, decimals)} US$`;
};

export const formatCompactNumber = (value: number | null | undefined): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return 'N/A';
  return new Intl.NumberFormat('en', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value);
};

export const formatBinary = (value: number | null | undefined): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return 'N/A';
  return value >= 1 ? 'Có' : 'Không';
};

export const formatRatio = (value: number | null | undefined, decimals = 3): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return 'N/A';
  return formatNumber(value, decimals);
};

export const formatIndicatorValue = (
  value: number | null | undefined,
  unit?: string | null,
  decimals = 2
): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return 'N/A';
  const normalized = (unit || '').trim().toLowerCase();
  if (!normalized) return formatNumber(value, decimals);
  if (normalized === '%') return formatPercent(value, decimals);
  if (normalized === 'ratio') return formatRatio(value, 3);
  if (normalized === '0/1') return formatBinary(value);
  if (normalized.includes('current us$')) return formatCurrencyCurrentUSD(value, 0);
  return formatNumber(value, decimals);
};

export const formatCellValue = (column: string, value: unknown, unit?: string): string => {
  if (YEAR_FIELD_RE.test(column)) return formatYear(value as number | string | null | undefined);
  if (typeof value === 'number') return formatIndicatorValue(value, unit);
  return formatNullable(value);
};

export const formatValue = (value: number | null | undefined, decimals = 2, suffix = ''): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return 'N/A';
  return `${formatNumber(value, decimals)}${suffix}`;
};

export const getAnomalyColor = (score: number | null | undefined): string => {
  if (score == null) return 'bg-slate-100 text-slate-600 border border-slate-200';
  if (score >= 0.9) return 'bg-red-100 text-red-700 border border-red-200';
  if (score >= 0.75) return 'bg-amber-100 text-amber-700 border border-amber-200';
  return 'bg-emerald-100 text-emerald-700 border border-emerald-200';
};
