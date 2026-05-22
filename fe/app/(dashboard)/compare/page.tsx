'use client';

import { Fragment, Suspense, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { BarChart3, Plus, Search, X } from 'lucide-react';
import PageHeader from '@/components/ui/PageHeader';
import FilterBar from '@/components/ui/FilterBar';
import SectionCard from '@/components/ui/SectionCard';
import TableShell from '@/components/ui/TableShell';
import StateBlock from '@/components/ui/StateBlock';
import { TableSkeleton } from '@/components/ui/Skeletons';
import { useCountries } from '@/lib/hooks/useCountries';
import { useIndicators } from '@/lib/hooks/useIndicators';
import { useCompare } from '@/lib/hooks/useCompare';
import { useUrlState } from '@/lib/hooks/useUrlState';
import { formatIndicatorValue, formatYear } from '@/lib/utils/format';
import { DEFAULT_COMPARE_COUNTRIES } from '@/lib/utils/compare';

const DEFAULT_INDICATOR = 'govdebt_GDP';
const DEFAULT_FROM = 2010;
const DEFAULT_TO = 2023;
const CHART_COLORS = ['#1d4ed8', '#b45309', '#0f766e', '#7c3aed', '#be123c'];

const buildLinearTrendByYear = (
  points: Array<{ year: number; value: number | null; trend_value?: number | null }>,
): Map<number, number | null> => {
  const explicitTrend = points.some((point) => point.trend_value != null);
  if (explicitTrend) {
    return new Map(points.map((point) => [point.year, point.trend_value ?? null]));
  }

  const valid = points.filter(
    (point): point is { year: number; value: number; trend_value?: number | null } =>
      point.value != null && Number.isFinite(point.value),
  );
  if (valid.length < 2) {
    return new Map(points.map((point) => [point.year, null]));
  }

  const n = valid.length;
  const sumX = valid.reduce((acc, point) => acc + point.year, 0);
  const sumY = valid.reduce((acc, point) => acc + point.value, 0);
  const sumXY = valid.reduce((acc, point) => acc + point.year * point.value, 0);
  const sumXX = valid.reduce((acc, point) => acc + point.year * point.year, 0);
  const denom = n * sumXX - sumX * sumX;
  if (denom === 0) {
    return new Map(points.map((point) => [point.year, null]));
  }

  const slope = (n * sumXY - sumX * sumY) / denom;
  const intercept = (sumY - slope * sumX) / n;
  return new Map(points.map((point) => [point.year, intercept + slope * point.year]));
};

export default function ComparePage() {
  return (
    <Suspense fallback={<TableSkeleton rows={8} />}>
      <ComparePageContent />
    </Suspense>
  );
}

function ComparePageContent() {
  const [countriesState, setCountriesState] = useUrlState<string[]>(
    'countries',
    [...DEFAULT_COMPARE_COUNTRIES],
  );
  const [indicatorState, setIndicatorState] = useUrlState<string>(
    'indicator',
    DEFAULT_INDICATOR,
  );
  const [fromState, setFromState] = useUrlState<number>('from', DEFAULT_FROM);
  const [toState, setToState] = useUrlState<number>('to', DEFAULT_TO);

  const [selectedCountries, setSelectedCountries] = useState<string[]>(countriesState);
  const [selectedIndicator, setSelectedIndicator] = useState(indicatorState);
  const [yearFrom, setYearFrom] = useState(fromState);
  const [yearTo, setYearTo] = useState(toState);
  const [countryKeyword, setCountryKeyword] = useState('');
  const [countryPickerOpen, setCountryPickerOpen] = useState(false);
  const countryPickerRef = useRef<HTMLDivElement>(null);

  const countriesQuery = useCountries();
  const indicatorsQuery = useIndicators();
  const compareQuery = useCompare(countriesState, indicatorState, fromState, toState);

  useEffect(() => {
    const handleOutside = (event: MouseEvent) => {
      if (!countryPickerRef.current) return;
      if (!countryPickerRef.current.contains(event.target as Node)) {
        setCountryPickerOpen(false);
      }
    };
    window.addEventListener('mousedown', handleOutside);
    return () => window.removeEventListener('mousedown', handleOutside);
  }, []);

  const selectableIndicators = useMemo(
    () => (indicatorsQuery.data || []).filter(item => item.supports_compare !== false),
    [indicatorsQuery.data],
  );
  const indicatorMeta = selectableIndicators.find(item => item.code === indicatorState);

  const yearOptions = useMemo(() => {
    const years: number[] = [];
    for (let year = 1980; year <= 2025; year += 1) years.push(year);
    return years;
  }, []);

  const selectedCountryDetails = useMemo(() => {
    const byCode = new Map((countriesQuery.data || []).map(item => [item.country_code, item]));
    return selectedCountries.map(code => byCode.get(code) || { country_code: code, country_name: code });
  }, [countriesQuery.data, selectedCountries]);

  const availableCountries = useMemo(() => {
    const all = countriesQuery.data || [];
    const keyword = countryKeyword.trim().toLowerCase();
    return all
      .filter(item => !selectedCountries.includes(item.country_code))
      .filter(item => {
        if (!keyword) return true;
        return (
          item.country_name.toLowerCase().includes(keyword) ||
          item.country_code.toLowerCase().includes(keyword)
        );
      })
      .slice(0, 50);
  }, [countriesQuery.data, countryKeyword, selectedCountries]);

  const chartRows = useMemo(() => {
    const grouped = compareQuery.data || {};
    const trendByCountry = new Map<string, Map<number, number | null>>();
    Object.entries(grouped).forEach(([countryCode, points]) => {
      trendByCountry.set(countryCode, buildLinearTrendByYear(points));
    });
    const years = new Set<number>();
    Object.values(grouped).forEach(items => {
      items.forEach(item => years.add(item.year));
    });
    return Array.from(years)
      .sort((a, b) => a - b)
      .map(year => {
        const row: Record<string, number | null> = { year };
        countriesState.forEach(countryCode => {
          const found = grouped[countryCode]?.find(item => item.year === year);
          row[countryCode] = found?.value ?? null;
          row[`${countryCode}__trend`] = trendByCountry.get(countryCode)?.get(year) ?? null;
        });
        return row;
      });
  }, [compareQuery.data, countriesState]);

  const applyFilters = () => {
    const validFrom = Math.min(yearFrom, yearTo);
    const validTo = Math.max(yearFrom, yearTo);
    setCountriesState(selectedCountries);
    setIndicatorState(selectedIndicator);
    setFromState(validFrom);
    setToState(validTo);
  };

  const canApply = selectedCountries.length >= 1 && !!selectedIndicator;
  const compareErrorMessage =
    compareQuery.error instanceof Error
      ? compareQuery.error.message
      : 'Không thể tải dữ liệu so sánh.';

  return (
    <div className="space-y-5">
      <PageHeader
        title="So sánh quốc gia"
        description="So sánh chỉ số kinh tế theo quốc gia và giai đoạn năm."
        actions={
          <Link
            href="/chat?q=So%20s%C3%A1nh%20n%E1%BB%A3%20c%C3%B4ng%20Vi%E1%BB%87t%20Nam%20v%C3%A0%20Th%C3%A1i%20Lan%20t%E1%BB%AB%202010%20%C4%91%E1%BA%BFn%202023"
            className="inline-flex items-center gap-2 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            <BarChart3 className="h-4 w-4" />
            Hỏi trợ lý AI
          </Link>
        }
      />

      <FilterBar>
        <div className="md:col-span-4">
          <label htmlFor="compare-indicator" className="mb-1 block text-sm font-medium text-slate-700">
            Chỉ số
          </label>
          <select
            id="compare-indicator"
            name="indicator"
            value={selectedIndicator}
            onChange={event => setSelectedIndicator(event.target.value)}
            className="h-10 w-full rounded-md border border-slate-300 px-3 text-sm"
          >
            {selectableIndicators.map(indicator => (
              <option key={indicator.code} value={indicator.code}>
                {indicator.name} ({indicator.code})
              </option>
            ))}
          </select>
        </div>

        <div className="md:col-span-2">
          <label htmlFor="compare-from" className="mb-1 block text-sm font-medium text-slate-700">
            Từ năm
          </label>
          <select
            id="compare-from"
            name="from"
            value={yearFrom}
            onChange={event => setYearFrom(Number(event.target.value))}
            className="h-10 w-full rounded-md border border-slate-300 px-3 text-sm"
          >
            {yearOptions.map(year => (
              <option key={year} value={year}>
                {year}
              </option>
            ))}
          </select>
        </div>

        <div className="md:col-span-2">
          <label htmlFor="compare-to" className="mb-1 block text-sm font-medium text-slate-700">
            Đến năm
          </label>
          <select
            id="compare-to"
            name="to"
            value={yearTo}
            onChange={event => setYearTo(Number(event.target.value))}
            className="h-10 w-full rounded-md border border-slate-300 px-3 text-sm"
          >
            {yearOptions.map(year => (
              <option key={year} value={year}>
                {year}
              </option>
            ))}
          </select>
        </div>

        <div className="md:col-span-4" ref={countryPickerRef}>
          <label htmlFor="compare-country-combobox" className="mb-1 block text-sm font-medium text-slate-700">
            Quốc gia
          </label>
          <div className="relative">
            <div className="flex min-h-10 flex-wrap items-center gap-1 rounded-md border border-slate-300 px-2 py-1">
              {selectedCountryDetails.map(item => (
                <span
                  key={item.country_code}
                  className="inline-flex items-center gap-1 rounded bg-slate-100 px-2 py-1 text-xs text-slate-700"
                >
                  {item.country_name} ({item.country_code})
                  <button
                    type="button"
                    onClick={() =>
                      setSelectedCountries(prev =>
                        prev.filter(code => code !== item.country_code),
                      )
                    }
                    className="rounded p-0.5 text-slate-500 hover:bg-slate-200 hover:text-slate-700"
                    aria-label={`Bỏ ${item.country_code}`}
                  >
                    <X className="h-3 w-3" />
                  </button>
                </span>
              ))}
              <div className="relative flex-1">
                <Search className="pointer-events-none absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  id="compare-country-combobox"
                  name="countries_search"
                  type="text"
                  role="combobox"
                  aria-expanded={countryPickerOpen}
                  aria-controls="compare-country-listbox"
                  aria-autocomplete="list"
                  value={countryKeyword}
                  onFocus={() => setCountryPickerOpen(true)}
                  onClick={() => setCountryPickerOpen(true)}
                  onChange={event => {
                    setCountryKeyword(event.target.value);
                    setCountryPickerOpen(true);
                  }}
                  placeholder="Bấm để xem tất cả hoặc gõ để lọc"
                  className="h-8 w-full rounded px-8 text-sm outline-none"
                />
              </div>
            </div>
            {countryPickerOpen ? (
              <div
                id="compare-country-listbox"
                role="listbox"
                className="absolute z-20 mt-1 max-h-56 w-full overflow-y-auto rounded-md border border-slate-300 bg-white shadow-lg"
              >
                {availableCountries.length === 0 ? (
                  <p className="px-3 py-2 text-sm text-slate-500">Không có quốc gia phù hợp.</p>
                ) : (
                  availableCountries.map(country => (
                    <button
                      key={country.country_code}
                      type="button"
                      role="option"
                      aria-selected={false}
                      onClick={() => {
                        if (selectedCountries.length >= 5) return;
                        setSelectedCountries(prev => [...prev, country.country_code]);
                        setCountryKeyword('');
                        setCountryPickerOpen(true);
                      }}
                      className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-slate-50"
                    >
                      <span>
                        {country.country_name} ({country.country_code})
                      </span>
                      <Plus className="h-3.5 w-3.5 text-slate-400" />
                    </button>
                  ))
                )}
              </div>
            ) : null}
          </div>
          <p className="mt-1 text-xs text-slate-500">
            Chọn tối thiểu 1 quốc gia, khuyến nghị 2 quốc gia để so sánh.
          </p>
        </div>

        <div className="md:col-span-12 flex items-center gap-2">
          <button
            type="button"
            onClick={applyFilters}
            disabled={!canApply}
            className="rounded-md bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-900 disabled:cursor-not-allowed disabled:bg-slate-400"
          >
            Áp dụng
          </button>
        </div>
      </FilterBar>

      {compareQuery.isLoading || countriesQuery.isLoading || indicatorsQuery.isLoading ? (
        <TableSkeleton rows={6} />
      ) : null}

      {compareQuery.error ? (
        <StateBlock
          mode="error"
          title="Không tải được dữ liệu so sánh"
          description={
            compareErrorMessage.includes('chưa hỗ trợ')
              ? 'Chỉ số này chưa có dữ liệu so sánh phù hợp.'
              : compareErrorMessage
          }
        />
      ) : null}

      {!compareQuery.isLoading && !compareQuery.error && chartRows.length === 0 ? (
        <StateBlock
          mode="empty"
          title="Chưa có dữ liệu phù hợp"
          description="Hãy điều chỉnh quốc gia, chỉ số hoặc giai đoạn năm."
        />
      ) : null}

      {!compareQuery.isLoading && !compareQuery.error && chartRows.length > 0 ? (
        <>
          <SectionCard
            title={`Biểu đồ so sánh: ${indicatorMeta?.name || indicatorState}`}
            description={`Đơn vị: ${indicatorMeta?.unit || 'N/A'}`}
          >
            <div className="h-[320px] min-w-0 w-full">
              <ResponsiveContainer width="100%" height={320}>
                <LineChart data={chartRows}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="year" />
                  <YAxis />
                  <Tooltip
                    formatter={value =>
                      formatIndicatorValue(
                        typeof value === 'number'
                          ? value
                          : value == null
                            ? null
                            : Number(value),
                        indicatorMeta?.unit,
                      )
                    }
                    labelFormatter={label => `Năm ${label}`}
                  />
                  <Legend />
                  {countriesState.map((countryCode, index) => (
                    <Fragment key={`${countryCode}-series`}>
                      <Line
                        type="monotone"
                        dataKey={countryCode}
                        stroke={CHART_COLORS[index % CHART_COLORS.length]}
                        strokeWidth={2}
                        dot={false}
                        connectNulls
                      />
                      {chartRows.some(row => row[`${countryCode}__trend`] != null) ? (
                        <Line
                          type="monotone"
                          dataKey={`${countryCode}__trend`}
                          name={`${countryCode} (xu hướng)`}
                          stroke={CHART_COLORS[index % CHART_COLORS.length]}
                          strokeWidth={2}
                          strokeDasharray="6 4"
                          dot={false}
                          connectNulls
                        />
                      ) : null}
                    </Fragment>
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </SectionCard>

          <TableShell>
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className="px-3 py-2 text-left font-semibold">Năm</th>
                  {countriesState.map(countryCode => (
                    <th key={countryCode} className="px-3 py-2 text-right font-semibold">
                      {countryCode}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {chartRows.map(row => (
                  <tr key={`year-${row.year}`} className="hover:bg-slate-50">
                    <td className="px-3 py-2 font-mono">{formatYear(row.year as number)}</td>
                    {countriesState.map(countryCode => (
                      <td key={`${row.year}-${countryCode}`} className="px-3 py-2 text-right">
                        {formatIndicatorValue(
                          row[countryCode] as number | null,
                          indicatorMeta?.unit,
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </TableShell>
          <p className="text-xs text-slate-500">
            Chỉ số đang so sánh: {compareQuery.indicatorName} ({compareQuery.requestedIndicator}) | Đơn vị:{' '}
            {compareQuery.indicatorUnit || 'Chưa công bố'}
          </p>
        </>
      ) : null}
    </div>
  );
}
