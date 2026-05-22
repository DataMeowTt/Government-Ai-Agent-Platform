export const DEFAULT_COMPARE_COUNTRIES = ['USA', 'AUS'] as const;

export const buildCompareCountries = (primaryCountry?: string): string[] => {
  const ordered = [primaryCountry, ...DEFAULT_COMPARE_COUNTRIES].filter(Boolean) as string[];
  const seen = new Set<string>();
  const deduped: string[] = [];
  ordered.forEach((code) => {
    const normalized = code.toUpperCase();
    if (seen.has(normalized)) return;
    seen.add(normalized);
    deduped.push(normalized);
  });
  return deduped;
};
