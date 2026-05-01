'use client';
import { useMemo } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine } from 'recharts';
import { CountryAnalyticsRow } from '@/lib/types';
import TabMetricsList from './TabMetricsList';
import TabYearlyTable from './TabYearlyTable';

export default function RiskTabContent({ data }: { data: CountryAnalyticsRow[] }) {
  const chartData = useMemo(() => data.filter(d => d.actual_reer_deviation != null).map(d => ({ year: d.year, reer: d.actual_reer_deviation, isAnomaly: (d.anomaly_reer_deviation ?? 0) >= 0.75 })), [data]);
  const metrics = useMemo(() => chartData.length ? [{ label: 'Độ lệch REER cực đại', value: `${Math.max(...chartData.map(d => Math.abs(d.reer ?? 0))).toFixed(2)}%` }] : [], [chartData]);

  if (!chartData.length) return <div className="p-8 text-center text-slate-500 border border-dashed border-slate-300 rounded-md">Không có dữ liệu rủi ro.</div>;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 bg-white rounded-md border border-slate-200 p-4">
          <h3 className="text-base font-semibold text-slate-800 mb-3">Độ lệch tỷ giá REER (%)</h3>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="year" stroke="#64748b" fontSize={12} />
              <YAxis stroke="#64748b" fontSize={12} tickFormatter={v => `${v}%`} />
              <Tooltip formatter={(v: any) => v != null ? `${Number(v).toFixed(2)}%` : 'N/A'} />
              <Legend />
              <Line type="monotone" dataKey="reer" name="REER Deviation" stroke="#ef4444" strokeWidth={2} dot={{ r: 3 }} />
              {chartData.filter(d => d.isAnomaly).map(p => <ReferenceLine key={p.year} x={p.year} stroke="#f59e0b" strokeDasharray="3 3" />)}
            </LineChart>
          </ResponsiveContainer>
        </div>
        <TabMetricsList metrics={metrics} />
      </div>
      <TabYearlyTable data={data.slice(-8).map(d => ({ year: d.year, actual_reer_deviation: d.actual_reer_deviation, anomaly_reer_deviation: d.anomaly_reer_deviation }))} columns={[{ accessor: 'actual_reer_deviation', header: 'REER Deviation (%)' }, { accessor: 'anomaly_reer_deviation', header: 'Điểm bất thường' }]} />
    </div>
  );
}
