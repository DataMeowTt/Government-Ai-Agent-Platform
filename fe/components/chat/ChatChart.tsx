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
const tertiaryColor = '#7c3aed';

const seriesPalette = [chartColor, secondaryColor, tertiaryColor];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function getChartData(chart?: AiAgentChartConfig) {
  if (!Array.isArray(chart?.data)) {
    return [];
  }
  return chart.data.filter(isRecord);
}

function getValidYKeys(chart: AiAgentChartConfig, data: Record<string, unknown>[]) {
  if (!Array.isArray(chart.yKeys) || chart.yKeys.length === 0) {
    return [];
  }

  const keys = chart.yKeys
    .map((key) => String(key || '').trim())
    .filter(Boolean);
  if (keys.length === 0) {
    return [];
  }

  const set = new Set(keys);
  return Array.from(set).filter((key) =>
    data.some((row) => {
      const value = row[key];
      return typeof value === 'number' && Number.isFinite(value);
    })
  );
}

function getValidXKey(chart: AiAgentChartConfig, data: Record<string, unknown>[]) {
  const key = String(chart.xKey || '').trim();
  if (!key) {
    return null;
  }
  const hasValue = data.some((row) => row[key] !== undefined && row[key] !== null && String(row[key]).trim() !== '');
  return hasValue ? key : null;
}

export default function ChatChart({ chart }: { chart?: AiAgentChartConfig }) {
  const data = getChartData(chart);
  const chartType = chart?.type?.toLowerCase();

  if (!chart || !chartType || chartType === 'none' || chartType === 'table' || data.length === 0) {
    return null;
  }

  if (chartType !== 'line' && chartType !== 'bar') {
    return null;
  }

  const xKey = getValidXKey(chart, data);
  const yKeys = getValidYKeys(chart, data);
  if (!xKey || yKeys.length === 0) {
    return null;
  }

  if (chartType === 'bar') {
    return (
      <div className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-3">
        {chart.title ? <h4 className="mb-3 text-sm font-semibold text-slate-900">{chart.title}</h4> : null}
        <div className="h-72 min-h-[260px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey={xKey} tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip />
              {yKeys.length > 1 ? <Legend /> : null}
              {yKeys.map((key, index) => (
                <Bar
                  key={key}
                  dataKey={key}
                  fill={seriesPalette[index % seriesPalette.length]}
                  radius={[4, 4, 0, 0]}
                />
              ))}
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
        <div className="h-72 min-h-[260px] w-full">
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
                  stroke={seriesPalette[index % seriesPalette.length]}
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
