'use client';
import { useMemo } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { CountryAnalyticsRow } from '@/lib/types';
import TabMetricsList from './TabMetricsList';
import TabYearlyTable from './TabYearlyTable';

export default function SocialTabContent({ data }: { data: CountryAnalyticsRow[] }) {
  const chartData = useMemo(() => data.filter(d => d.actual_poverty != null || d.actual_unemployment != null).map(d => ({ year: d.year, poverty: d.actual_poverty, unemployment: d.actual_unemployment })), [data]);
  const metrics = useMemo(() => {
    const valid = data.filter(d => d.actual_unemployment != null);
    return valid.length ? [{ label: 'Thất nghiệp trung bình', value: `${(valid.reduce((s, d) => s + (d.actual_unemployment ?? 0), 0) / valid.length).toFixed(2)}%` }] : [];
  }, [data]);

  if (!chartData.length) return <div className="p-8 text-center text-slate-500 border border-dashed border-slate-300 rounded-md">Không có dữ liệu xã hội.</div>;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 bg-white rounded-md border border-slate-200 p-4">
          <h3 className="text-base font-semibold text-slate-800 mb-3">Nghèo đói & Thất nghiệp (%)</h3>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="year" stroke="#64748b" fontSize={12} />
              <YAxis stroke="#64748b" fontSize={12} tickFormatter={v => `${v}%`} />
              <Tooltip formatter={(v: any) => v != null ? `${Number(v).toFixed(2)}%` : 'N/A'} />
              <Legend />
              <Line type="monotone" dataKey="poverty" name="Nghèo đói" stroke="#ef4444" strokeWidth={2} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="unemployment" name="Thất nghiệp" stroke="#06b6d4" strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <TabMetricsList metrics={metrics} />
      </div>
      <TabYearlyTable data={data.slice(-8).map(d => ({ year: d.year, actual_poverty: d.actual_poverty, actual_unemployment: d.actual_unemployment }))} columns={[{ accessor: 'actual_poverty', header: 'Nghèo đói (%)' }, { accessor: 'actual_unemployment', header: 'Thất nghiệp (%)' }]} />
    </div>
  );
}
