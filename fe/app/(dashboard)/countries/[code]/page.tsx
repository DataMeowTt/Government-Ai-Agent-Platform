'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
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
import { BarChart3, Database, Info } from 'lucide-react';
import PageHeader from '@/components/ui/PageHeader';
import SectionCard from '@/components/ui/SectionCard';
import StateBlock from '@/components/ui/StateBlock';
import TableShell from '@/components/ui/TableShell';
import Pagination from '@/components/ui/Pagination';
import SearchInput from '@/components/ui/SearchInput';
import { ChartSkeleton, TableSkeleton } from '@/components/ui/Skeletons';
import {
  useCountries,
  useCountryAnalytics,
  useCountryIndicators,
  useClusterBenchmark,
} from '@/lib/hooks/useCountries';
import { formatIndicatorValue, formatNullable, formatNumber, formatYear } from '@/lib/utils/format';

const KPI_CODES = [
  'rGDP_growth_YoY',
  'govdebt_GDP',
  'inflation_cpi',
  'unemployment_total',
  'poverty_headcount',
];
const TABLE_PAGE_SIZE = 20;

type SeriesPoint = {
  year: number;
  value: number | null;
};

function resolveCompletenessPercent(meta?: {
  data_completeness?: number | null;
  data_completeness_ratio?: number | null;
  data_completeness_percent?: number | null;
}) {
  if (!meta) return null;
  if (meta.data_completeness_percent != null && Number.isFinite(meta.data_completeness_percent)) {
    return meta.data_completeness_percent;
  }
  if (meta.data_completeness != null && Number.isFinite(meta.data_completeness)) {
    return meta.data_completeness <= 1 ? meta.data_completeness * 100 : meta.data_completeness;
  }
  if (meta.data_completeness_ratio != null && Number.isFinite(meta.data_completeness_ratio)) {
    return meta.data_completeness_ratio * 100;
  }
  return null;
}

export default function CountryDetailPage() {
  const params = useParams();
  const code = String(params.code || '').toUpperCase();
  const countriesQuery = useCountries();
  const analyticsQuery = useCountryAnalytics(code);
  const indicatorsQuery = useCountryIndicators(code);

  const rows = useMemo(() => indicatorsQuery.data?.rows || [], [indicatorsQuery.data?.rows]);
  const country = countriesQuery.data?.find(item => item.country_code === code);
  const countryName = country?.country_name || code;
  const completenessPercent = resolveCompletenessPercent(analyticsQuery.data?.meta);
  const latestYear =
    analyticsQuery.data?.meta.latest_year ??
    (rows.length ? Math.max(...rows.map(item => item.year)) : null);

  const indicatorSeries = useMemo(() => {
    const grouped = new Map<
      string,
      { indicator: string; indicator_name: string; category: string; unit: string; points: SeriesPoint[] }
    >();
    rows.forEach(row => {
      const current = grouped.get(row.indicator) || {
        indicator: row.indicator,
        indicator_name: row.indicator_name || row.indicator,
        category: row.category || 'Khác',
        unit: row.unit || '',
        points: [],
      };
      current.points.push({ year: row.year, value: row.value });
      grouped.set(row.indicator, current);
    });
    return Array.from(grouped.values())
      .map(item => ({
        ...item,
        points: item.points.slice().sort((a, b) => a.year - b.year),
      }))
      .sort((a, b) => a.indicator_name.localeCompare(b.indicator_name));
  }, [rows]);

  const yearBounds = useMemo(() => {
    if (!rows.length) return { min: 2000, max: 2025 };
    return {
      min: Math.min(...rows.map(item => item.year)),
      max: Math.max(...rows.map(item => item.year)),
    };
  }, [rows]);

  const [selectedIndicatorState, setSelectedIndicator] = useState<string>('');
  const [fromYearState, setFromYear] = useState<number | null>(null);
  const [toYearState, setToYear] = useState<number | null>(null);
  const [tableSearch, setTableSearch] = useState('');
  const [tablePage, setTablePage] = useState(1);

  const selectedIndicator =
    selectedIndicatorState && indicatorSeries.some(item => item.indicator === selectedIndicatorState)
      ? selectedIndicatorState
      : (indicatorSeries[0]?.indicator ?? '');
  const fromYear = fromYearState ?? yearBounds.min;
  const toYear = toYearState ?? yearBounds.max;
  const safeRangeFrom = Math.min(fromYear, toYear);
  const safeRangeTo = Math.max(fromYear, toYear);

  const selectedSeries =
    indicatorSeries.find(item => item.indicator === selectedIndicator) || null;
  const filteredSeriesPoints = (selectedSeries?.points || []).filter(
    point => point.year >= safeRangeFrom && point.year <= safeRangeTo,
  );

  const allYears = useMemo(() => {
    const years: number[] = [];
    for (let year = yearBounds.min; year <= yearBounds.max; year += 1) years.push(year);
    return years;
  }, [yearBounds]);

  const groupedIndicators = useMemo(() => {
    const map = new Map<string, typeof indicatorSeries>();
    indicatorSeries.forEach(series => {
      const list = map.get(series.category) || [];
      list.push(series);
      map.set(series.category, list);
    });
    return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [indicatorSeries]);

  const kpiCards = useMemo(() => {
    return KPI_CODES.map(codeValue => {
      const series = indicatorSeries.find(item => item.indicator === codeValue);
      if (!series) return null;
      const latest = series.points
        .slice()
        .reverse()
        .find(point => point.value != null);
      return {
        ...series,
        latestYear: latest?.year ?? null,
        latestValue: latest?.value ?? null,
      };
    }).filter(Boolean) as Array<{
      indicator: string;
      indicator_name: string;
      unit: string;
      latestYear: number | null;
      latestValue: number | null;
    }>;
  }, [indicatorSeries]);

  const tableRows = useMemo(() => {
    const keyword = tableSearch.trim().toLowerCase();
    const filtered = rows.filter(row => {
      if (!keyword) return true;
      return (
        row.indicator.toLowerCase().includes(keyword) ||
        row.indicator_name.toLowerCase().includes(keyword) ||
        row.category.toLowerCase().includes(keyword)
      );
    });
    return filtered.sort((a, b) => {
      if (a.indicator !== b.indicator) return a.indicator.localeCompare(b.indicator);
      return b.year - a.year;
    });
  }, [rows, tableSearch]);
  const totalTablePages = Math.max(1, Math.ceil(tableRows.length / TABLE_PAGE_SIZE));
  const safeTablePage = Math.min(Math.max(tablePage, 1), totalTablePages);
  const pagedTableRows = tableRows.slice(
    (safeTablePage - 1) * TABLE_PAGE_SIZE,
    safeTablePage * TABLE_PAGE_SIZE,
  );

  const anomalies = useMemo(() => {
    const analyticsRows = analyticsQuery.data?.data || [];
    const result: Array<{
      year: number;
      indicatorLabel: string;
      indicatorCode: string;
      value: number | null;
      unit: string;
      score: number | null;
    }> = [];
    analyticsRows.forEach(item => {
      if ((item.anomaly_growth ?? 0) >= 0.75) {
        result.push({
          year: item.year,
          indicatorLabel: 'Tăng trưởng GDP thực',
          indicatorCode: 'rGDP_growth_YoY',
          value: item.actual_growth ?? null,
          unit: '%',
          score: item.anomaly_growth ?? null,
        });
      }
      if ((item.anomaly_debt ?? 0) >= 0.75) {
        result.push({
          year: item.year,
          indicatorLabel: 'Nợ công/GDP',
          indicatorCode: 'govdebt_GDP',
          value: item.actual_debt ?? null,
          unit: '%',
          score: item.anomaly_debt ?? null,
        });
      }
      if ((item.anomaly_reer_deviation ?? 0) >= 0.75) {
        result.push({
          year: item.year,
          indicatorLabel: 'Độ lệch REER',
          indicatorCode: 'REER_deviation',
          value: item.actual_reer_deviation ?? null,
          unit: '%',
          score: item.anomaly_reer_deviation ?? null,
        });
      }
    });
    return result.sort((a, b) => b.year - a.year).slice(0, 15);
  }, [analyticsQuery.data?.data]);

  const benchmarkQuery = useClusterBenchmark(code, 'govdebt_GDP', latestYear ?? undefined);

  if (analyticsQuery.isLoading || countriesQuery.isLoading || indicatorsQuery.isLoading) {
    return (
      <div className="space-y-4">
        <ChartSkeleton />
        <TableSkeleton rows={8} />
      </div>
    );
  }

  if (analyticsQuery.isError || indicatorsQuery.isError) {
    return (
      <StateBlock
        mode="error"
        title="Không tải được hồ sơ quốc gia"
        description={
          analyticsQuery.error instanceof Error
            ? analyticsQuery.error.message
            : indicatorsQuery.error instanceof Error
              ? indicatorsQuery.error.message
              : 'Lỗi không xác định'
        }
      />
    );
  }

  if (!rows.length) {
    return (
      <StateBlock
        mode="empty"
        title="Chưa có dữ liệu phù hợp"
        description="Hiện chưa có chuỗi dữ liệu chỉ số cho quốc gia này."
      />
    );
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title={`Hồ sơ kinh tế quốc gia: ${countryName} (${code})`}
        description={latestYear ? `Dữ liệu cập nhật đến năm ${formatYear(latestYear)}` : 'Chưa có thông tin năm cập nhật'}
        actions={
          <div className="flex items-center gap-2">
            <Link
              href={`/compare?countries=${code}&indicator=govdebt_GDP&from=2010&to=2023`}
              className="inline-flex items-center gap-2 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              <BarChart3 className="h-4 w-4" />
              So sánh
            </Link>
            <Link
              href={`/chat?q=${encodeURIComponent(`Phân tích hồ sơ kinh tế của ${countryName} (${code}) theo các chỉ số nổi bật.`)}`}
              className="inline-flex items-center gap-2 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              <Database className="h-4 w-4" />
              Phân tích bằng trợ lý dữ liệu
            </Link>
          </div>
        }
      />

      <SectionCard title="Thông tin quốc gia">
        <div className="grid grid-cols-1 gap-3 text-sm md:grid-cols-4">
          <div>
            <p className="text-slate-500">Mã quốc gia</p>
            <p className="font-medium text-slate-900">{code}</p>
          </div>
          <div>
            <p className="text-slate-500">Tên quốc gia</p>
            <p className="font-medium text-slate-900">{countryName}</p>
          </div>
          <div>
            <p className="text-slate-500">Khu vực</p>
            <p className="font-medium text-slate-900">
              {formatNullable(country?.region, 'Chưa có thông tin công bố')}
            </p>
          </div>
          <div>
            <p className="inline-flex items-center gap-1 text-slate-500">
              Mức đầy đủ dữ liệu
              <span title="Đây là tỷ lệ bao phủ dữ liệu (coverage), không phải điểm đánh giá chất lượng nội dung.">
                <Info className="h-3.5 w-3.5" />
              </span>
            </p>
            <p className="font-medium text-slate-900">
              {completenessPercent == null ? 'Chưa có dữ liệu phù hợp' : `${formatNumber(completenessPercent, 2)}%`}
            </p>
          </div>
        </div>
      </SectionCard>

      <section className="grid grid-cols-1 gap-3 lg:grid-cols-5">
        {kpiCards.map(item => (
          <article key={item.indicator} className="rounded-md border border-slate-200 bg-white px-4 py-3 shadow-sm">
            <p className="text-xs font-medium text-slate-600">{item.indicator_name}</p>
            <p className="mt-2 text-lg font-semibold text-slate-900">
              {item.latestValue == null ? 'Chưa có dữ liệu phù hợp' : formatIndicatorValue(item.latestValue, item.unit)}
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Năm: {item.latestYear ? formatYear(item.latestYear) : 'Chưa có'} | {item.indicator}
            </p>
          </article>
        ))}
      </section>

      <SectionCard title="Bộ lọc phân tích">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
          <div>
            <label htmlFor="country-indicator" className="mb-1 block text-sm font-medium text-slate-700">
              Chỉ số
            </label>
            <select
              id="country-indicator"
              name="indicator"
              value={selectedIndicator}
              onChange={event => setSelectedIndicator(event.target.value)}
              className="h-10 w-full rounded-md border border-slate-300 px-3 text-sm"
            >
              {indicatorSeries.map(item => (
                <option key={item.indicator} value={item.indicator}>
                  {item.indicator_name} ({item.indicator})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="country-from-year" className="mb-1 block text-sm font-medium text-slate-700">
              Từ năm
            </label>
            <select
              id="country-from-year"
              name="from_year"
              value={fromYear}
              onChange={event => setFromYear(Number(event.target.value))}
              className="h-10 w-full rounded-md border border-slate-300 px-3 text-sm"
            >
              {allYears.map(year => (
                <option key={year} value={year}>
                  {formatYear(year)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="country-to-year" className="mb-1 block text-sm font-medium text-slate-700">
              Đến năm
            </label>
            <select
              id="country-to-year"
              name="to_year"
              value={toYear}
              onChange={event => setToYear(Number(event.target.value))}
              className="h-10 w-full rounded-md border border-slate-300 px-3 text-sm"
            >
              {allYears.map(year => (
                <option key={year} value={year}>
                  {formatYear(year)}
                </option>
              ))}
            </select>
          </div>
          <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
            {selectedSeries ? (
              <>
                <p className="font-medium text-slate-800">{selectedSeries.indicator_name}</p>
                <p>Category: {selectedSeries.category}</p>
                <p>Unit: {selectedSeries.unit || 'N/A'}</p>
                <p>Code: {selectedSeries.indicator}</p>
              </>
            ) : (
              <p>Chưa có dữ liệu phù hợp.</p>
            )}
          </div>
        </div>
      </SectionCard>

      <SectionCard
        title={selectedSeries ? `Xu hướng: ${selectedSeries.indicator_name}` : 'Xu hướng chỉ số'}
        description={selectedSeries ? `Đơn vị: ${selectedSeries.unit || 'N/A'}` : undefined}
      >
        {filteredSeriesPoints.length === 0 ? (
          <StateBlock mode="empty" title="Chưa có dữ liệu phù hợp" description="Hãy điều chỉnh chỉ số hoặc khoảng năm." />
        ) : (
          <div className="h-[320px] min-w-0 w-full">
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={filteredSeriesPoints}>
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
                      selectedSeries?.unit,
                    )
                  }
                  labelFormatter={label => `Năm ${formatYear(label as number)}`}
                />
                <Legend />
                <Line type="monotone" dataKey="value" name={selectedSeries?.indicator_name || 'Giá trị'} stroke="#1d4ed8" strokeWidth={2} dot={false} connectNulls />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </SectionCard>

      <SectionCard title="Bảng dữ liệu đầy đủ">
        <div className="mb-3">
          <SearchInput
            id="country-indicator-search"
            name="indicator_search"
            label="Tìm chỉ số"
            value={tableSearch}
            onChange={value => {
              setTableSearch(value);
              setTablePage(1);
            }}
            placeholder="Lọc theo tên chỉ số, mã hoặc nhóm"
          />
        </div>
        <TableShell>
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className="px-3 py-2 text-left font-semibold">Năm</th>
                <th className="px-3 py-2 text-left font-semibold">Chỉ số</th>
                <th className="px-3 py-2 text-left font-semibold">Nhóm</th>
                <th className="px-3 py-2 text-right font-semibold">Giá trị</th>
                <th className="px-3 py-2 text-left font-semibold">Đơn vị</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white">
              {pagedTableRows.map(item => (
                <tr key={`${item.indicator}-${item.year}`} className="hover:bg-slate-50">
                  <td className="px-3 py-2 font-mono">{formatYear(item.year)}</td>
                  <td className="px-3 py-2">
                    {item.indicator_name}
                    <p className="text-xs text-slate-500">{item.indicator}</p>
                  </td>
                  <td className="px-3 py-2">{item.category}</td>
                  <td className="px-3 py-2 text-right">
                    {item.value == null ? 'Chưa có dữ liệu phù hợp' : formatIndicatorValue(item.value, item.unit)}
                  </td>
                  <td className="px-3 py-2">{item.unit || 'N/A'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableShell>
        <Pagination
          currentPage={safeTablePage}
          totalPages={totalTablePages}
          onPageChange={setTablePage}
          totalItems={tableRows.length}
          itemsPerPage={TABLE_PAGE_SIZE}
        />
      </SectionCard>

      <SectionCard title="Chỉ số theo nhóm">
        <div className="space-y-4">
          {groupedIndicators.map(([category, items]) => (
            <article key={category} className="rounded-md border border-slate-200 bg-slate-50 p-3">
              <h3 className="text-sm font-semibold text-slate-900">{category}</h3>
              <div className="mt-2 grid grid-cols-1 gap-2 lg:grid-cols-2">
                {items.map(item => {
                  const latest = item.points.slice().reverse().find(point => point.value != null);
                  return (
                    <div key={item.indicator} className="rounded-md border border-slate-200 bg-white px-3 py-2">
                      <p className="text-sm font-medium text-slate-900">{item.indicator_name}</p>
                      <p className="text-xs text-slate-500">{item.indicator}</p>
                      <p className="mt-1 text-sm text-slate-700">
                        {latest && latest.value != null
                          ? `${formatIndicatorValue(latest.value, item.unit)} (năm ${formatYear(latest.year)})`
                          : 'Chưa có dữ liệu phù hợp'}
                      </p>
                    </div>
                  );
                })}
              </div>
            </article>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="So sánh trong cụm theo chỉ số nợ công/GDP">
        {benchmarkQuery.isLoading ? (
          <p className="text-sm text-slate-600">Đang tải dữ liệu so sánh trong cụm...</p>
        ) : benchmarkQuery.isError || !benchmarkQuery.data ? (
          <p className="text-sm text-slate-600">Chưa có dữ liệu so sánh trong cụm cho quốc gia này.</p>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-slate-700">
              Cụm {benchmarkQuery.data.cluster_id} | Năm {formatYear(benchmarkQuery.data.year)} | Trung bình cụm:{' '}
              {formatIndicatorValue(benchmarkQuery.data.average, '%')}
            </p>
            <TableShell>
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="px-3 py-2 text-left font-semibold">Quốc gia</th>
                    <th className="px-3 py-2 text-left font-semibold">Mã</th>
                    <th className="px-3 py-2 text-right font-semibold">Giá trị</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {benchmarkQuery.data.members.slice(0, 12).map(member => (
                    <tr key={`${member.country_code}-${member.year}`}>
                      <td className="px-3 py-2">{member.country_name || member.country_code}</td>
                      <td className="px-3 py-2 font-mono">{member.country_code}</td>
                      <td className="px-3 py-2 text-right">{formatIndicatorValue(member.value, '%')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableShell>
          </div>
        )}
      </SectionCard>

      <SectionCard title="Bất thường dữ liệu của quốc gia">
        {anomalies.length === 0 ? (
          <p className="text-sm text-slate-600">Không phát hiện bản ghi có điểm bất thường thống kê từ 0,75 trở lên.</p>
        ) : (
          <TableShell>
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className="px-3 py-2 text-left font-semibold">Năm</th>
                  <th className="px-3 py-2 text-left font-semibold">Chỉ số</th>
                  <th className="px-3 py-2 text-right font-semibold">Giá trị</th>
                  <th className="px-3 py-2 text-right font-semibold">Điểm bất thường thống kê</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {anomalies.map(item => (
                  <tr key={`${item.indicatorCode}-${item.year}-${item.score ?? 0}`} className="hover:bg-slate-50">
                    <td className="px-3 py-2 font-mono">{formatYear(item.year)}</td>
                    <td className="px-3 py-2">
                      {item.indicatorLabel}
                      <p className="text-xs text-slate-500">{item.indicatorCode}</p>
                    </td>
                    <td className="px-3 py-2 text-right">{formatIndicatorValue(item.value, item.unit)}</td>
                    <td className="px-3 py-2 text-right">{formatNumber(item.score, 3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableShell>
        )}
      </SectionCard>
    </div>
  );
}
