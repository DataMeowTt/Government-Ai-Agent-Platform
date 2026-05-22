'use client';
import { useMemo } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine } from 'recharts';
import { CountryAnalyticsRow } from '@/lib/types';
import TabMetricsList from './TabMetricsList';
import TabYearlyTable from './TabYearlyTable';

export default function GrowthTabContent({ data }: { data: CountryAnalyticsRow[] }) {
  const chartData = useMemo(() => data.map(d => ({
    year: d.year, actual: d.actual_growth, trend: d.trend_growth, isAnomaly: (d.anomaly_growth ?? 0) >= 0.75
  })), [data]);

  const metrics = useMemo(() => {
    const valid = data.filter(d => d.actual_growth != null);
    if (!valid.length) return [];
    const avg5y = valid.slice(-5).reduce((s, d) => s + (d.actual_growth ?? 0), 0) / Math.min(valid.length, 5);
    return [
      { label: 'Trung bình 5 năm', value: `${avg5y.toFixed(2)}%`, status: 'ok' as const },
      { label: 'Cao nhất', value: `${Math.max(...valid.map(d => d.actual_growth ?? -Infinity)).toFixed(2)}%` },
      { label: 'Thấp nhất', value: `${Math.min(...valid.map(d => d.actual_growth ?? Infinity)).toFixed(2)}%` },
    ];
  }, [data]);

  const tableData = useMemo(() => data.slice(-8).map(d => ({ year: d.year, actual_growth: d.actual_growth, trend_growth: d.trend_growth })), [data]);

  if (!data.some(d => d.actual_growth != null)) return <div className="p-8 text-center text-slate-500 border border-dashed border-slate-300 rounded-md">Không có dữ liệu tăng trưởng.</div>;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 bg-white rounded-md border border-slate-200 p-4">
          <h3 className="text-base font-semibold text-slate-800 mb-3">Diễn biến Tăng trưởng GDP thực tế (%)</h3>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="year" stroke="#64748b" fontSize={12} />
              <YAxis stroke="#64748b" fontSize={12} tickFormatter={v => `${v}%`} />
              <Tooltip formatter={(v: any) => v != null ? `${Number(v).toFixed(2)}%` : 'N/A'} />
              <Legend />
              <Line type="monotone" dataKey="actual" name="Thực tế" stroke="#3b82f6" strokeWidth={2} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="trend" name="Xu hướng" stroke="#10b981" strokeWidth={2} strokeDasharray="5 5" dot={false} />
              {chartData.filter(d => d.isAnomaly).map(p => <ReferenceLine key={p.year} x={p.year} stroke="#ef4444" strokeDasharray="3 3" />)}
            </LineChart>
          </ResponsiveContainer>
        </div>
        <TabMetricsList metrics={metrics} />
      </div>
      <TabYearlyTable data={tableData} columns={[{ accessor: 'actual_growth', header: 'Tăng trưởng (%)' }, { accessor: 'trend_growth', header: 'Xu hướng (%)' }]} />
    </div>
  );
}
