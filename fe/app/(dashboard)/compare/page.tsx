'use client';
import { Suspense, useMemo, useState } from 'react';
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
import PageHeader from '@/components/ui/PageHeader';
import FilterBar from '@/components/ui/FilterBar';
import SectionCard from '@/components/ui/SectionCard';
import TableShell from '@/components/ui/TableShell';
import StateBlock from '@/components/ui/StateBlock';
import { TableSkeleton } from '@/components/ui/Skeletons';
import SearchInput from '@/components/ui/SearchInput';
import { useCountries } from '@/lib/hooks/useCountries';
import { useIndicators } from '@/lib/hooks/useIndicators';
import { useCompare } from '@/lib/hooks/useCompare';
import { useUrlState } from '@/lib/hooks/useUrlState';
import { formatIndicatorValue, formatYear } from '@/lib/utils/format';

const DEFAULT_COUNTRIES = ['VNM', 'THA'];
const DEFAULT_INDICATOR = 'govdebt_GDP';
const DEFAULT_FROM = 2010;
const DEFAULT_TO = 2023;

const CHART_COLORS = ['#1d4ed8', '#b45309', '#0f766e', '#7c3aed', '#be123c'];

export default function ComparePage() {
  return (
    <Suspense fallback={<TableSkeleton rows={8} />}>
      <ComparePageContent />
    </Suspense>
  );
}

function ComparePageContent() {
  const [countriesState, setCountriesState] = useUrlState<string[]>('countries', DEFAULT_COUNTRIES);
  const [indicatorState, setIndicatorState] = useUrlState<string>('indicator', DEFAULT_INDICATOR);
  const [fromState, setFromState] = useUrlState<number>('from', DEFAULT_FROM);
  const [toState, setToState] = useUrlState<number>('to', DEFAULT_TO);

  const [selectedCountries, setSelectedCountries] = useState<string[]>(countriesState);
  const [selectedIndicator, setSelectedIndicator] = useState(indicatorState);
  const [yearFrom, setYearFrom] = useState(fromState);
  const [yearTo, setYearTo] = useState(toState);
  const [search, setSearch] = useState('');

  const countriesQuery = useCountries();
  const indicatorsQuery = useIndicators();
  const compareQuery = useCompare(countriesState, indicatorState);

  const indicatorMeta = indicatorsQuery.data?.find((item) => item.code === indicatorState);
  const filteredCountries = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    const list = countriesQuery.data || [];
    if (!keyword) return list;
    return list.filter(
      (item) =>
        item.country_name.toLowerCase().includes(keyword) || item.country_code.toLowerCase().includes(keyword)
    );
  }, [countriesQuery.data, search]);

  const yearOptions = useMemo(() => {
    const years: number[] = [];
    for (let year = 1980; year <= 2025; year += 1) years.push(year);
    return years;
  }, []);

  const chartRows = useMemo(() => {
    const grouped = compareQuery.data || {};
    const years = new Set<number>();
    Object.values(grouped).forEach((items) => {
      items.forEach((item) => {
        if (item.year >= fromState && item.year <= toState) years.add(item.year);
      });
    });
    return Array.from(years)
      .sort((a, b) => a - b)
      .map((year) => {
        const row: Record<string, number | null> = { year };
        countriesState.forEach((countryCode) => {
          const found = grouped[countryCode]?.find((item) => item.year === year);
          row[countryCode] = found?.value ?? null;
        });
        return row;
      });
  }, [compareQuery.data, countriesState, fromState, toState]);

  const applyFilters = () => {
    const validFrom = Math.min(yearFrom, yearTo);
    const validTo = Math.max(yearFrom, yearTo);
    setCountriesState(selectedCountries);
    setIndicatorState(selectedIndicator);
    setFromState(validFrom);
    setToState(validTo);
  };

  const canApply = selectedCountries.length > 0 && !!selectedIndicator;

  return (
    <div className="space-y-5">
      <PageHeader
        title="So sánh quốc gia"
        description="So sánh chỉ số kinh tế theo quốc gia và giai đoạn năm."
        actions={
          <Link
            href="/chat?q=So%20s%C3%A1nh%20n%E1%BB%A3%20c%C3%B4ng%20Vi%E1%BB%87t%20Nam%20v%C3%A0%20Th%C3%A1i%20Lan%20t%E1%BB%AB%202010%20%C4%91%E1%BA%BFn%202023"
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Hỏi trợ lý AI
          </Link>
        }
      />

      <FilterBar>
        <div className="md:col-span-4">
          <label className="mb-1 block text-sm font-medium text-slate-700">Chỉ số</label>
          <select
            value={selectedIndicator}
            onChange={(event) => setSelectedIndicator(event.target.value)}
            className="h-10 w-full rounded-md border border-slate-300 px-3 text-sm"
          >
            {(indicatorsQuery.data || []).map((indicator) => (
              <option key={indicator.code} value={indicator.code}>
                {indicator.name} ({indicator.code})
              </option>
            ))}
          </select>
        </div>

        <div className="md:col-span-2">
          <label className="mb-1 block text-sm font-medium text-slate-700">Từ năm</label>
          <select
            value={yearFrom}
            onChange={(event) => setYearFrom(Number(event.target.value))}
            className="h-10 w-full rounded-md border border-slate-300 px-3 text-sm"
          >
            {yearOptions.map((year) => (
              <option key={year} value={year}>
                {year}
              </option>
            ))}
          </select>
        </div>

        <div className="md:col-span-2">
          <label className="mb-1 block text-sm font-medium text-slate-700">Đến năm</label>
          <select
            value={yearTo}
            onChange={(event) => setYearTo(Number(event.target.value))}
            className="h-10 w-full rounded-md border border-slate-300 px-3 text-sm"
          >
            {yearOptions.map((year) => (
              <option key={year} value={year}>
                {year}
              </option>
            ))}
          </select>
        </div>

        <div className="md:col-span-4">
          <label className="mb-1 block text-sm font-medium text-slate-700">Quốc gia (tối đa 5)</label>
          <SearchInput
            value={search}
            onChange={setSearch}
            placeholder="Tìm theo tên hoặc mã quốc gia"
            debounceTime={150}
          />
          <div className="mt-2 max-h-36 overflow-y-auto rounded-md border border-slate-300 bg-white p-2">
            {filteredCountries.map((country) => {
              const checked = selectedCountries.includes(country.country_code);
              return (
                <label
                  key={country.country_code}
                  className="flex cursor-pointer items-center justify-between rounded px-2 py-1.5 text-sm hover:bg-slate-50"
                >
                  <span>
                    {country.country_name} ({country.country_code})
                  </span>
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => {
                      if (checked) {
                        setSelectedCountries(selectedCountries.filter((item) => item !== country.country_code));
                        return;
                      }
                      if (selectedCountries.length >= 5) return;
                      setSelectedCountries([...selectedCountries, country.country_code]);
                    }}
                  />
                </label>
              );
            })}
          </div>
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

      <div className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
        Trang này so sánh một chỉ số duy nhất giữa các quốc gia theo giai đoạn năm đã chọn.
      </div>

      {compareQuery.isLoading || countriesQuery.isLoading || indicatorsQuery.isLoading ? <TableSkeleton rows={6} /> : null}

      {compareQuery.error ? (
        <StateBlock
          mode="error"
          title="Không tải được dữ liệu so sánh"
          description={compareQuery.error instanceof Error ? compareQuery.error.message : 'Lỗi không xác định'}
        />
      ) : null}

      {!compareQuery.isLoading && !compareQuery.error && compareQuery.unsupportedIndicator ? (
        <StateBlock
          mode="empty"
          title="Chỉ số chưa hỗ trợ cho màn hình so sánh"
          description={`Chỉ số ${compareQuery.requestedIndicator} hiện chưa có cấu trúc dữ liệu phù hợp để so sánh theo thời gian.`}
        />
      ) : null}

      {!compareQuery.isLoading && !compareQuery.error && !compareQuery.unsupportedIndicator && chartRows.length === 0 ? (
        <StateBlock
          mode="empty"
          title="Không có dữ liệu trong phạm vi lọc"
          description="Hãy thử điều chỉnh quốc gia, chỉ số hoặc giai đoạn năm."
        />
      ) : null}

      {!compareQuery.isLoading && !compareQuery.error && !compareQuery.unsupportedIndicator && chartRows.length > 0 ? (
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
                    formatter={(value) =>
                      formatIndicatorValue(
                        typeof value === 'number' ? value : value == null ? null : Number(value),
                        indicatorMeta?.unit
                      )
                    }
                    labelFormatter={(label) => `Năm ${label}`}
                  />
                  <Legend />
                  {countriesState.map((countryCode, index) => (
                    <Line
                      key={countryCode}
                      type="monotone"
                      dataKey={countryCode}
                      stroke={CHART_COLORS[index % CHART_COLORS.length]}
                      strokeWidth={2}
                      dot={false}
                      connectNulls
                    />
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
                  {countriesState.map((countryCode) => (
                    <th key={countryCode} className="px-3 py-2 text-right font-semibold">
                      {countryCode}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {chartRows.map((row) => (
                  <tr key={`year-${row.year}`} className="hover:bg-slate-50">
                    <td className="px-3 py-2 font-mono">{formatYear(row.year as number)}</td>
                    {countriesState.map((countryCode) => (
                      <td key={`${row.year}-${countryCode}`} className="px-3 py-2 text-right">
                        {formatIndicatorValue(row[countryCode] as number | null, indicatorMeta?.unit)}
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
