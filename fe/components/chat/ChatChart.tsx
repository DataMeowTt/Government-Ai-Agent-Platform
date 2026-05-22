'use client';

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { AiAgentChartConfig } from '@/lib/types/aiChat';

const chartColor = '#2563eb';
const secondaryColor = '#0f766e';

function getChartData(chart?: AiAgentChartConfig) {
  return Array.isArray(chart?.data) ? chart.data : [];
}

function getYKeys(chart: AiAgentChartConfig) {
  if (Array.isArray(chart.yKeys) && chart.yKeys.length > 0) {
    return chart.yKeys;
  }

  return ['value'];
}

export default function ChatChart({ chart }: { chart?: AiAgentChartConfig }) {
  const data = getChartData(chart);
  const chartType = chart?.type?.toLowerCase();

  if (!chart || chartType === 'none' || data.length === 0) {
    return null;
  }

  const xKey = chart.xKey || (chartType === 'line' ? 'year' : 'country_code');
  const yKeys = getYKeys(chart);

  if (chartType === 'bar') {
    return (
      <div className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-3">
        {chart.title ? <h4 className="mb-3 text-sm font-semibold text-slate-900">{chart.title}</h4> : null}
        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey={xKey} tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey={yKeys[0]} fill={chartColor} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    );
  }

  if (chartType === 'line') {
    return (
      <div className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-3">
        {chart.title ? <h4 className="mb-3 text-sm font-semibold text-slate-900">{chart.title}</h4> : null}
        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey={xKey} tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip />
              <Legend />
              {yKeys.map((key, index) => (
                <Line
                  key={key}
                  type="monotone"
                  dataKey={key}
                  stroke={index === 0 ? chartColor : secondaryColor}
                  strokeWidth={2}
                  dot={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    );
  }

  return null;
}
