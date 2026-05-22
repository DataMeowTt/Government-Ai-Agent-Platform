'use client';
import { useMemo } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { CountryAnalyticsRow } from '@/lib/types';
import TabMetricsList from './TabMetricsList';
import TabYearlyTable from './TabYearlyTable';

export default function FiscalTabContent({ data }: { data: CountryAnalyticsRow[] }) {
  const chartData = useMemo(() => data.filter(d => d.actual_debt != null || d.actual_inflation != null).map(d => ({ year: d.year, debt: d.actual_debt, inflation: d.actual_inflation })), [data]);
  const metrics = useMemo(() => {
    const validDebt = data.filter(d => d.actual_debt != null);
    const avgDebt = validDebt.length ? validDebt.reduce((s, d) => s + (d.actual_debt ?? 0), 0) / validDebt.length : 0;
    return [{ label: 'Nợ công trung bình', value: `${avgDebt.toFixed(1)}%` }];
  }, [data]);

  if (!chartData.length) return <div className="p-8 text-center text-slate-500 border border-dashed border-slate-300 rounded-md">Không có dữ liệu tài khóa.</div>;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 bg-white rounded-md border border-slate-200 p-4">
          <h3 className="text-base font-semibold text-slate-800 mb-3">Nợ công & Lạm phát CPI (%)</h3>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="year" stroke="#64748b" fontSize={12} />
              <YAxis stroke="#64748b" fontSize={12} tickFormatter={v => `${v}%`} />
              <Tooltip formatter={(v: any) => v != null ? `${Number(v).toFixed(2)}%` : 'N/A'} />
              <Legend />
              <Line type="monotone" dataKey="debt" name="Nợ công" stroke="#f59e0b" strokeWidth={2} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="inflation" name="Lạm phát CPI" stroke="#8b5cf6" strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <TabMetricsList metrics={metrics} />
      </div>
      <TabYearlyTable data={data.slice(-8).map(d => ({ year: d.year, actual_debt: d.actual_debt, actual_inflation: d.actual_inflation }))} columns={[{ accessor: 'actual_debt', header: 'Nợ công (%)' }, { accessor: 'actual_inflation', header: 'Lạm phát CPI (%)' }]} />
    </div>
  );
}
