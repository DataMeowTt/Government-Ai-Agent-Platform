'use client';
import { getIndicatorViName } from '@/lib/utils/indicatorTranslations';
import { Country, Indicator } from '@/lib/types';
import { useUrlState } from '@/lib/hooks/useUrlState';
import { useCompare } from '@/lib/hooks/useCompare';
import { useIndicators } from '@/lib/hooks/useIndicators';
import { useCountries } from '@/lib/hooks/useCountries';
import { ChartSkeleton, TableSkeleton } from '@/components/ui/Skeletons';
import { useState, useMemo, useEffect, useRef } from 'react';
import { Search, X, Calendar, BarChart3, Table2, AlertCircle, ArrowDownToLine, Plus } from 'lucide-react';
import { cn } from '@/lib/utils/cn';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from 'recharts';

const CHART_COLORS = ['#3b82f6', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6', '#06b6d4', '#ec4899', '#64748b'];

export default function ComparePage() {
  const [rawCountries, setRawCountries] = useUrlState<string[]>('countries', []);
  const [selectedIndicator, setSelectedIndicator] = useUrlState<string>('indicator', 'rGDP_growth_YoY');
  const [yearFrom, setYearFrom] = useUrlState<number>('from', 2000);
  const [yearTo, setYearTo] = useUrlState<number>('to', 2022);
  const [viewMode, setViewMode] = useState<'chart' | 'table'>('chart');
  const [isApplying, setIsApplying] = useState(false);

  const [countrySearch, setCountrySearch] = useState('');
  const [isSearchFocused, setIsSearchFocused] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const { data: countries, isLoading: loadingCountries } = useCountries();
  const { data: indicators } = useIndicators();
  const [displayCountries, setDisplayCountries] = useState(rawCountries);
  const [displayIndicator, setDisplayIndicator] = useState(selectedIndicator);

  const { data: chartData, isLoading: loadingChart } = useCompare(displayCountries, displayIndicator);

  const applyFilters = () => {
    setIsApplying(true);
    setDisplayCountries(rawCountries);
    setDisplayIndicator(selectedIndicator);
    setTimeout(() => setIsApplying(false), 500);
  };

  const toggleCountry = (code: string) => {
    if (rawCountries.includes(code)) setRawCountries(rawCountries.filter(c => c !== code));
    else if (rawCountries.length < 5) setRawCountries([...rawCountries, code]);
    setCountrySearch('');
    setIsSearchFocused(false);
  };

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsSearchFocused(false);
        setCountrySearch('');
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const currentIndicatorMeta = indicators?.find(i => i.code === displayIndicator);
  const indicatorLabel = currentIndicatorMeta
    ? `${getIndicatorViName(currentIndicatorMeta.code)} (${currentIndicatorMeta.unit})`
    : displayIndicator;

  const missingDataWarning = displayCountries.some(c => !chartData[c] || chartData[c].length === 0);

  const chartRows = useMemo(() => {
    if (!chartData || Object.keys(chartData).length === 0) return [];
    const years = new Set<number>();
    Object.values(chartData).forEach(arr =>
      arr.forEach(p => { if (p.year >= yearFrom && p.year <= yearTo) years.add(p.year); })
    );
    return Array.from(years).sort((a, b) => a - b).map(year => {
      const row: Record<string, number | null> = { year };
      displayCountries.forEach(code => {
        row[code] = chartData[code]?.find(p => p.year === year)?.value ?? null;
      });
      return row;
    });
  }, [chartData, displayCountries, yearFrom, yearTo]);

  const tableRows = useMemo(() => {
    const years = new Set<number>();
    Object.values(chartData || {}).forEach(arr => arr.forEach(p => { if (p.year >= yearFrom && p.year <= yearTo) years.add(p.year); }));
    return Array.from(years).sort().map(year => {
      const row: Record<string, number | string> = { year };
      displayCountries.forEach(code => {
        const val = chartData[code]?.find(p => p.year === year)?.value;
        row[code] = val != null ? val : 'N/A';
      });
      return row;
    });
  }, [chartData, displayCountries, yearFrom, yearTo]);

  const availableCountries = (countries as Country[] | undefined)?.filter((c: Country) =>
    !rawCountries.includes(c.country_code) &&
    (c.country_name.toLowerCase().includes(countrySearch.toLowerCase()) || c.country_code.toLowerCase().includes(countrySearch.toLowerCase()))
  ) || [];

  const yearOptions = Array.from({ length: 2026 - 2000 }, (_, i) => 2000 + i);

  if (loadingCountries) return <TableSkeleton rows={1} />;

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-indigo-50 rounded-md text-indigo-600">
            <BarChart3 className="w-6 h-6" />
          </div>
          <h1 className="text-2xl font-bold text-gray-900">So sánh Đa Quốc gia</h1>
        </div>
      </div>

      <div className="bg-white p-6 rounded-md border border-gray-200 shadow-sm space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-5 space-y-3">
            <label className="block text-sm font-medium text-gray-700">Chọn Quốc gia (Tối đa 5)</label>
            <div className="flex flex-wrap gap-2 min-h-[40px] p-2 border border-gray-200 rounded-md bg-gray-50">
              {rawCountries.map(code => {
                const c = (countries as Country[] | undefined)?.find((ct: Country) => ct.country_code === code);
                return (
                  <span key={code} className="inline-flex items-center gap-1 px-2 py-1 bg-blue-100 text-blue-800 text-xs font-medium rounded-full">
                    {c?.country_name || code} ({code})
                    <button onClick={() => toggleCountry(code)} className="ml-1 hover:text-blue-900"><X className="w-3 h-3" /></button>
                  </span>
                );
              })}
              {rawCountries.length === 0 && <span className="text-xs text-gray-400 py-1">Chưa chọn quốc gia nào</span>}
            </div>
            <div className="relative" ref={dropdownRef}>
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                placeholder="Tìm hoặc chọn quốc gia..."
                value={countrySearch}
                onChange={(e) => setCountrySearch(e.target.value)}
                onFocus={() => setIsSearchFocused(true)}
                className="w-full pl-10 pr-4 h-10 border border-gray-300 rounded-md text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              {(isSearchFocused || countrySearch) && availableCountries.length > 0 && (
                <div className="absolute z-10 w-full mt-1 bg-white border border-gray-200 rounded-md shadow-lg max-h-48 overflow-y-auto">
                  {availableCountries.map(c => (
                    <button
                      key={c.country_code}
                      onMouseDown={(e) => { e.preventDefault(); toggleCountry(c.country_code); }}
                      className="w-full px-3 py-2 text-left text-sm hover:bg-gray-100 border-b border-gray-100 last:border-0"
                    >
                      {c.country_name} <span className="text-gray-500 text-xs">({c.country_code})</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="lg:col-span-4 space-y-3">
            <label className="block text-sm font-medium text-gray-700">Chỉ số & Giai đoạn</label>
            <select value={selectedIndicator} onChange={(e) => setSelectedIndicator(e.target.value)} className="w-full h-10 border border-gray-300 rounded-md text-sm bg-white px-3 focus:outline-none focus:ring-2 focus:ring-blue-500">
              {(indicators as Indicator[] | undefined)?.filter(i =>
                ['Growth', 'Fiscal', 'Monetary', 'Social', 'Risk', 'Structure', 'Trade', 'Demographics', 'Investment', 'Quality', 'Other'].includes(i.category)
              ).map(i => (
                <option key={i.code} value={i.code}>
                  {getIndicatorViName(i.code)} ({i.unit})
                </option>
              ))}
            </select>
            <div className="flex items-center gap-3 mt-2">
              <div className="flex-1">
                <span className="text-xs text-gray-500 block mb-1">Từ năm</span>
                <select value={yearFrom} onChange={(e) => setYearFrom(Number(e.target.value))} className="w-full h-9 border border-gray-300 rounded px-2 text-sm bg-white">
                  {yearOptions.map(y => <option key={y} value={y}>{y}</option>)}
                </select>
              </div>
              <Calendar className="w-4 h-4 text-gray-400 mt-4" />
              <div className="flex-1">
                <span className="text-xs text-gray-500 block mb-1">Đến năm</span>
                <select value={yearTo} onChange={(e) => setYearTo(Number(e.target.value))} className="w-full h-9 border border-gray-300 rounded px-2 text-sm bg-white">
                  {yearOptions.map(y => <option key={y} value={y}>{y}</option>)}
                </select>
              </div>
            </div>
          </div>

          <div className="lg:col-span-3 flex flex-col justify-end gap-3">
            <button onClick={applyFilters} disabled={rawCountries.length === 0 || isApplying} className="w-full h-10 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 disabled:opacity-50 transition-colors flex items-center justify-center gap-2">
              <Plus className="w-4 h-4" /> Áp dụng so sánh
            </button>
            <button onClick={() => setViewMode(viewMode === 'chart' ? 'table' : 'chart')} className="w-full h-10 border border-gray-300 text-gray-700 text-sm font-medium rounded-md hover:bg-gray-50 transition-colors flex items-center justify-center gap-2">
              {viewMode === 'chart' ? <Table2 className="w-4 h-4" /> : <BarChart3 className="w-4 h-4" />}
              {viewMode === 'chart' ? 'Dạng bảng' : 'Dạng biểu đồ'}
            </button>
          </div>
        </div>

        {missingDataWarning && (
          <div className="flex items-start gap-3 p-3 bg-amber-50 border border-amber-200 rounded-md text-amber-800 text-sm">
            <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
            <span>Một hoặc nhiều quốc gia thiếu dữ liệu trong khoảng năm đã chọn. Biểu đồ sẽ hiện gián đoạn.</span>
          </div>
        )}

        {loadingChart ? (
          viewMode === 'chart' ? <ChartSkeleton /> : <TableSkeleton rows={5} />
        ) : (
          <>
            {viewMode === 'chart' ? (
              displayCountries.length > 0 ? (
                <div className="bg-white rounded-md border border-gray-200 p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="font-semibold text-gray-900">{indicatorLabel}</h3>
                    <button className="text-xs text-gray-500 hover:text-gray-700 flex items-center gap-1"><ArrowDownToLine className="w-3 h-3" /> Xuất PNG</button>
                  </div>
                  <ResponsiveContainer width="100%" height={350}>
                    <LineChart data={chartRows}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                      <XAxis dataKey="year" stroke="#6b7280" fontSize={12} />
                      <YAxis stroke="#6b7280" fontSize={12} />
                      <Tooltip />
                      <Legend />
                      {displayCountries.map((code, idx) => (
                        <Line
                          key={`${code}-line-${displayIndicator}`}
                          type="monotone"
                          dataKey={code}
                          name={code}
                          stroke={CHART_COLORS[idx % CHART_COLORS.length]}
                          strokeWidth={2}
                          dot={{ r: 3 }}
                          activeDot={{ r: 5 }}
                          connectNulls={false}
                        />
                      ))}
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <div className="h-64 flex items-center justify-center bg-gray-50 rounded border border-dashed border-gray-300 text-gray-500">Chọn quốc gia và nhấn Áp dụng để bắt đầu.</div>
              )
            ) : (
              <div className="bg-white rounded-md border border-gray-200 overflow-hidden">
                <table className="min-w-full divide-y divide-gray-200 text-sm">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 text-left font-semibold text-gray-600">Năm</th>
                      {displayCountries.map(c => <th key={c} className="px-4 py-3 text-left font-semibold text-gray-600">{c}</th>)}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {tableRows.map(row => (
                      <tr key={row.year} className="hover:bg-gray-50">
                        <td className="px-4 py-2 font-mono text-gray-700">{row.year}</td>
                        {displayCountries.map(c => (
                          <td key={c} className={cn('px-4 py-2 font-medium', typeof row[c] === 'number' ? 'text-gray-900' : 'text-gray-400')}>{typeof row[c] === 'number' ? (row[c] as number).toFixed(2) : 'N/A'}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}