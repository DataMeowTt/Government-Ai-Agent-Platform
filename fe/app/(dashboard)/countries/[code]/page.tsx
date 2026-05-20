'use client';
import { useEffect, useMemo, useState } from 'react';
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
import PageHeader from '@/components/ui/PageHeader';
import SectionCard from '@/components/ui/SectionCard';
import StateBlock from '@/components/ui/StateBlock';
import TableShell from '@/components/ui/TableShell';
import { ChartSkeleton, TableSkeleton } from '@/components/ui/Skeletons';
import { useCountries, useCountryAnalytics, useClusterBenchmark } from '@/lib/hooks/useCountries';
import { formatIndicatorValue, formatNullable, formatNumber, formatYear } from '@/lib/utils/format';

type IndicatorDefinition = {
  id: string;
  label: string;
  rowKey:
    | 'actual_growth'
    | 'actual_debt'
    | 'actual_inflation'
    | 'actual_unemployment'
    | 'actual_poverty'
    | 'actual_reer_deviation'
    | 'actual_manuf_share'
    | 'actual_agri_share';
  unit: string;
  group: 'Tăng trưởng' | 'Tài khóa - tiền tệ' | 'Rủi ro khủng hoảng' | 'Phúc lợi xã hội' | 'Cơ cấu kinh tế';
  description: string;
};

const INDICATORS: IndicatorDefinition[] = [
  {
    id: 'rGDP_growth_YoY',
    label: 'Tăng trưởng GDP thực',
    rowKey: 'actual_growth',
    unit: '%',
    group: 'Tăng trưởng',
    description: 'Mức tăng trưởng sản lượng thực của nền kinh tế theo năm.',
  },
  {
    id: 'govdebt_GDP',
    label: 'Nợ công/GDP',
    rowKey: 'actual_debt',
    unit: '%',
    group: 'Tài khóa - tiền tệ',
    description: 'Tỷ lệ nợ công trên GDP, phản ánh sức ép nợ của khu vực công.',
  },
  {
    id: 'inflation_cpi',
    label: 'Lạm phát CPI',
    rowKey: 'actual_inflation',
    unit: '%',
    group: 'Tài khóa - tiền tệ',
    description: 'Mức biến động chỉ số giá tiêu dùng theo năm.',
  },
  {
    id: 'unemployment_total',
    label: 'Thất nghiệp',
    rowKey: 'actual_unemployment',
    unit: '%',
    group: 'Phúc lợi xã hội',
    description: 'Tỷ lệ lao động thất nghiệp trong lực lượng lao động.',
  },
  {
    id: 'poverty_headcount',
    label: 'Nghèo đa chiều',
    rowKey: 'actual_poverty',
    unit: '%',
    group: 'Phúc lợi xã hội',
    description: 'Tỷ lệ dân số thuộc nhóm nghèo theo ngưỡng dữ liệu hiện có.',
  },
  {
    id: 'REER_deviation',
    label: 'Độ lệch REER',
    rowKey: 'actual_reer_deviation',
    unit: '%',
    group: 'Rủi ro khủng hoảng',
    description: 'Mức lệch của tỷ giá thực hiệu lực so với nền tảng dài hạn.',
  },
  {
    id: 'manuf_va_share',
    label: 'Tỷ trọng công nghiệp chế biến',
    rowKey: 'actual_manuf_share',
    unit: '%',
    group: 'Cơ cấu kinh tế',
    description: 'Tỷ trọng giá trị gia tăng công nghiệp chế biến trong cơ cấu kinh tế.',
  },
  {
    id: 'agri_va_share',
    label: 'Tỷ trọng nông nghiệp',
    rowKey: 'actual_agri_share',
    unit: '%',
    group: 'Cơ cấu kinh tế',
    description: 'Tỷ trọng giá trị gia tăng khu vực nông nghiệp trong cơ cấu kinh tế.',
  },
];

const KPI_INDICATORS = ['rGDP_growth_YoY', 'govdebt_GDP', 'inflation_cpi', 'unemployment_total', 'poverty_headcount'];

type CountryAnomalyRow = {
  year: number;
  indicatorLabel: string;
  indicatorCode: string;
  value: number | null;
  unit: string;
  score: number | null;
};

export default function CountryDetailPage() {
  const params = useParams();
  const code = String(params.code || '').toUpperCase();
  const countriesQuery = useCountries();
  const analyticsQuery = useCountryAnalytics(code);
  const rows = analyticsQuery.data?.data || [];

  const country = countriesQuery.data?.find((item) => item.country_code === code);
  const countryName = country?.country_name || code;
  const latestYear = analyticsQuery.data?.meta.latest_year ?? (rows.length ? rows[rows.length - 1].year : null);

  const yearRange = useMemo(() => {
    if (!rows.length) return { min: 2000, max: 2025 };
    return {
      min: Math.min(...rows.map((item) => item.year)),
      max: Math.max(...rows.map((item) => item.year)),
    };
  }, [rows]);

  const availableIndicators = useMemo(
    () => INDICATORS.filter((indicator) => rows.some((row) => row[indicator.rowKey] != null)),
    [rows]
  );

  const [selectedIndicator, setSelectedIndicator] = useState<string>('govdebt_GDP');
  const [fromYear, setFromYear] = useState<number>(yearRange.min);
  const [toYear, setToYear] = useState<number>(yearRange.max);

  useEffect(() => {
    setFromYear(yearRange.min);
    setToYear(yearRange.max);
  }, [yearRange.min, yearRange.max]);

  useEffect(() => {
    if (availableIndicators.length === 0) return;
    const existing = availableIndicators.find((item) => item.id === selectedIndicator);
    if (!existing) setSelectedIndicator(availableIndicators[0].id);
  }, [availableIndicators, selectedIndicator]);

  const selectedIndicatorMeta = availableIndicators.find((item) => item.id === selectedIndicator) || null;
  const filteredRows = rows.filter((item) => item.year >= Math.min(fromYear, toYear) && item.year <= Math.max(fromYear, toYear));

  const kpiCards = KPI_INDICATORS.map((kpiCode) => {
    const meta = INDICATORS.find((item) => item.id === kpiCode);
    if (!meta) return null;
    const latest = rows
      .slice()
      .reverse()
      .find((item) => item[meta.rowKey] != null);
    return {
      ...meta,
      value: latest ? (latest[meta.rowKey] as number | null) : null,
      year: latest?.year ?? null,
    };
  }).filter(Boolean) as Array<IndicatorDefinition & { value: number | null; year: number | null }>;

  const chartRows = useMemo(() => {
    if (!selectedIndicatorMeta) return [];
    return filteredRows
      .map((item) => ({
        year: item.year,
        value: (item[selectedIndicatorMeta.rowKey] as number | null | undefined) ?? null,
        trend: selectedIndicatorMeta.rowKey === 'actual_growth' ? item.trend_growth ?? null : null,
      }))
      .sort((a, b) => a.year - b.year);
  }, [filteredRows, selectedIndicatorMeta]);

  const groupedIndicators = useMemo(() => {
    const groups = new Map<string, Array<IndicatorDefinition & { latestValue: number | null; latestYear: number | null }>>();
    availableIndicators.forEach((indicator) => {
      const latest = rows
        .slice()
        .reverse()
        .find((item) => item[indicator.rowKey] != null);
      const row = {
        ...indicator,
        latestValue: latest ? (latest[indicator.rowKey] as number | null) : null,
        latestYear: latest?.year ?? null,
      };
      if (!groups.has(indicator.group)) groups.set(indicator.group, []);
      groups.get(indicator.group)!.push(row);
    });
    return Array.from(groups.entries());
  }, [availableIndicators, rows]);

  const anomalies = useMemo<CountryAnomalyRow[]>(() => {
    const result: CountryAnomalyRow[] = [];
    rows.forEach((item) => {
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
  }, [rows]);

  const benchmarkIndicator = 'govdebt_GDP';
  const benchmarkQuery = useClusterBenchmark(code, benchmarkIndicator, latestYear ?? undefined);

  const years = useMemo(() => {
    const list: number[] = [];
    for (let year = yearRange.min; year <= yearRange.max; year += 1) list.push(year);
    return list;
  }, [yearRange.max, yearRange.min]);

  if (analyticsQuery.isLoading || countriesQuery.isLoading) {
    return (
      <div className="space-y-4">
        <ChartSkeleton />
        <TableSkeleton rows={8} />
      </div>
    );
  }

  if (analyticsQuery.isError) {
    return (
      <StateBlock
        mode="error"
        title="Không tải được hồ sơ quốc gia"
        description={analyticsQuery.error instanceof Error ? analyticsQuery.error.message : 'Lỗi không xác định'}
      />
    );
  }

  if (!rows.length) {
    return (
      <StateBlock
        mode="empty"
        title="Chưa có dữ liệu hồ sơ quốc gia"
        description="Hiện chưa có chuỗi dữ liệu phù hợp cho quốc gia này."
      />
    );
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title={`Hồ sơ kinh tế quốc gia: ${countryName} (${code})`}
        description={latestYear ? `Dữ liệu cập nhật đến năm ${formatYear(latestYear)}` : 'Thời điểm cập nhật hệ thống: chưa có thông tin công bố'}
        actions={
          <div className="flex items-center gap-2">
            <Link
              href={`/compare?countries=${code},THA&indicator=govdebt_GDP&from=2010&to=2023`}
              className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              So sánh với Thái Lan
            </Link>
            <Link
              href={`/chat?q=${encodeURIComponent(`Phân tích hồ sơ kinh tế của ${countryName} (${code}) dựa trên các chỉ số tăng trưởng, tài khóa, rủi ro và phúc lợi xã hội trong giai đoạn gần nhất.`)}`}
              className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
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
            <p className="font-medium text-slate-900">{formatNullable(country?.region, 'Chưa có thông tin công bố')}</p>
          </div>
          <div>
            <p className="text-slate-500">Mức đầy đủ dữ liệu</p>
            <p className="font-medium text-slate-900">
              {analyticsQuery.data?.meta.data_completeness != null
                ? `${formatNumber(analyticsQuery.data.meta.data_completeness, 2)}%`
                : 'Chưa có thông tin công bố'}
            </p>
          </div>
        </div>
      </SectionCard>

      <section className="grid grid-cols-1 gap-3 lg:grid-cols-6">
        {kpiCards.map((kpi) => (
          <article key={kpi.id} className="rounded-md border border-slate-200 bg-white px-4 py-3 shadow-sm">
            <p className="text-xs font-medium text-slate-600">{kpi.label}</p>
            <p className="mt-2 text-lg font-semibold text-slate-900">
              {kpi.value == null ? 'Chưa có dữ liệu phù hợp' : formatIndicatorValue(kpi.value, kpi.unit)}
            </p>
            <p className="mt-1 text-xs text-slate-500">
              {kpi.description} | Đơn vị: {kpi.unit || 'Chưa công bố'} | Năm: {kpi.year ? formatYear(kpi.year) : 'Chưa có'}
            </p>
          </article>
        ))}
        <article className="rounded-md border border-slate-200 bg-white px-4 py-3 shadow-sm">
          <p className="text-xs font-medium text-slate-600">Cụm cấu trúc</p>
          <p className="mt-2 text-lg font-semibold text-slate-900">
            {rows[rows.length - 1]?.cluster_id != null ? `Cụm ${rows[rows.length - 1].cluster_id}` : 'Chưa có dữ liệu phù hợp'}
          </p>
          <p className="mt-1 text-xs text-slate-500">Năm: {formatYear(rows[rows.length - 1]?.year)}</p>
        </article>
      </section>

      <SectionCard title="Giải thích cụm cấu trúc">
        <p className="text-sm leading-6 text-slate-700">
          Cụm không phải xếp hạng tốt/xấu; đây là nhóm quốc gia có cấu trúc kinh tế tương đồng trong cùng năm phân tích.
        </p>
      </SectionCard>

      <SectionCard title="Bộ lọc phân tích">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Chỉ số</label>
            <select
              value={selectedIndicator}
              onChange={(event) => setSelectedIndicator(event.target.value)}
              className="h-10 w-full rounded-md border border-slate-300 px-3 text-sm"
            >
              {availableIndicators.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Từ năm</label>
            <select
              value={fromYear}
              onChange={(event) => setFromYear(Number(event.target.value))}
              className="h-10 w-full rounded-md border border-slate-300 px-3 text-sm"
            >
              {years.map((year) => (
                <option key={year} value={year}>
                  {formatYear(year)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Đến năm</label>
            <select
              value={toYear}
              onChange={(event) => setToYear(Number(event.target.value))}
              className="h-10 w-full rounded-md border border-slate-300 px-3 text-sm"
            >
              {years.map((year) => (
                <option key={year} value={year}>
                  {formatYear(year)}
                </option>
              ))}
            </select>
          </div>
          <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
            {selectedIndicatorMeta ? (
              <>
                <p className="font-medium text-slate-800">{selectedIndicatorMeta.label}</p>
                <p>{selectedIndicatorMeta.description}</p>
                <p>Đơn vị: {selectedIndicatorMeta.unit || 'Chưa công bố'}</p>
              </>
            ) : (
              <p>Chưa có chỉ số phù hợp để hiển thị.</p>
            )}
          </div>
        </div>
      </SectionCard>

      <SectionCard
        title={selectedIndicatorMeta ? `Xu hướng: ${selectedIndicatorMeta.label}` : 'Xu hướng chỉ số'}
        description={selectedIndicatorMeta ? `Đơn vị: ${selectedIndicatorMeta.unit || 'Chưa công bố'}` : undefined}
      >
        {chartRows.length === 0 ? (
          <StateBlock
            mode="empty"
            title="Không có dữ liệu trong phạm vi lọc"
            description="Hãy mở rộng khoảng năm hoặc chọn chỉ số khác."
          />
        ) : (
          <div className="h-[320px] min-w-0 w-full">
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={chartRows}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="year" />
                <YAxis />
                <Tooltip
                  formatter={(value, name) => {
                    if (name === 'trend') return [formatIndicatorValue(value as number | null, selectedIndicatorMeta?.unit), 'Xu hướng'];
                    return [formatIndicatorValue(value as number | null, selectedIndicatorMeta?.unit), selectedIndicatorMeta?.label || 'Giá trị'];
                  }}
                  labelFormatter={(label) => `Năm ${formatYear(label as number)}`}
                />
                <Legend />
                <Line type="monotone" dataKey="value" name={selectedIndicatorMeta?.label || 'Giá trị'} stroke="#1d4ed8" strokeWidth={2} dot={false} connectNulls />
                {selectedIndicatorMeta?.rowKey === 'actual_growth' ? (
                  <Line type="monotone" dataKey="trend" name="Xu hướng" stroke="#0f766e" strokeWidth={2} dot={false} connectNulls />
                ) : null}
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </SectionCard>

      <SectionCard title="Bảng dữ liệu theo bộ lọc">
        {selectedIndicatorMeta ? (
          <TableShell>
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className="px-3 py-2 text-left font-semibold">Năm</th>
                  <th className="px-3 py-2 text-left font-semibold">Chỉ số</th>
                  <th className="px-3 py-2 text-right font-semibold">Giá trị</th>
                  <th className="px-3 py-2 text-left font-semibold">Đơn vị</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {filteredRows.map((item) => (
                  <tr key={`${item.country_code}-${item.year}`} className="hover:bg-slate-50">
                    <td className="px-3 py-2 font-mono">{formatYear(item.year)}</td>
                    <td className="px-3 py-2">{selectedIndicatorMeta.label}</td>
                    <td className="px-3 py-2 text-right">
                      {item[selectedIndicatorMeta.rowKey] == null
                        ? 'Chưa có dữ liệu phù hợp'
                        : formatIndicatorValue(item[selectedIndicatorMeta.rowKey] as number, selectedIndicatorMeta.unit)}
                    </td>
                    <td className="px-3 py-2">{selectedIndicatorMeta.unit || 'Chưa công bố'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableShell>
        ) : (
          <StateBlock
            mode="empty"
            title="Không có chỉ số khả dụng"
            description="Hiện chưa có chỉ số phù hợp cho quốc gia này."
          />
        )}
      </SectionCard>

      <SectionCard title="Các chỉ số theo nhóm">
        <div className="space-y-4">
          {groupedIndicators.map(([group, items]) => (
            <article key={group} className="rounded-md border border-slate-200 bg-slate-50 p-3">
              <h3 className="text-sm font-semibold text-slate-900">{group}</h3>
              <div className="mt-2 grid grid-cols-1 gap-2 lg:grid-cols-2">
                {items.map((item) => (
                  <div key={item.id} className="rounded-md border border-slate-200 bg-white px-3 py-2">
                    <p className="text-sm font-medium text-slate-900">{item.label}</p>
                    <p className="text-xs text-slate-500">{item.id}</p>
                    <p className="mt-1 text-sm text-slate-700">
                      {item.latestValue == null
                        ? 'Chưa có dữ liệu phù hợp'
                        : `${formatIndicatorValue(item.latestValue, item.unit)} (năm ${item.latestYear ? formatYear(item.latestYear) : 'chưa có'})`}
                    </p>
                    <p className="mt-1 text-xs text-slate-600">{item.description}</p>
                  </div>
                ))}
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
                  {benchmarkQuery.data.members.slice(0, 12).map((member) => (
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
                  <th className="px-3 py-2 text-right font-semibold">Thao tác</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {anomalies.map((item) => {
                  const prompt = encodeURIComponent(
                    `Phân tích bất thường của ${item.indicatorLabel} tại ${countryName} (${code}) năm ${formatYear(item.year)}. Giá trị: ${formatIndicatorValue(item.value, item.unit)}. Đơn vị: ${item.unit || 'chưa công bố'}. Điểm bất thường thống kê: ${formatNumber(item.score, 3)}. Hãy diễn giải ý nghĩa kinh tế và các khả năng cần kiểm tra thêm.`
                  );
                  return (
                    <tr key={`${item.indicatorCode}-${item.year}-${item.score ?? 0}`} className="hover:bg-slate-50">
                      <td className="px-3 py-2 font-mono">{formatYear(item.year)}</td>
                      <td className="px-3 py-2">
                        {item.indicatorLabel}
                        <p className="text-xs text-slate-500">{item.indicatorCode}</p>
                      </td>
                      <td className="px-3 py-2 text-right">{formatIndicatorValue(item.value, item.unit)}</td>
                      <td className="px-3 py-2 text-right">{formatNumber(item.score, 3)}</td>
                      <td className="px-3 py-2 text-right">
                        <Link
                          href={`/chat?q=${prompt}`}
                          className="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100"
                        >
                          Phân tích
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </TableShell>
        )}
      </SectionCard>
    </div>
  );
}
