'use client';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine
} from 'recharts';

interface DataPoint {
  year: number;
  actual: number | null;
  trend: number | null;
  anomaly?: number | null;
}

interface Props {
  data: DataPoint[];
  actualLabel?: string;
  trendLabel?: string;
  anomalyThreshold?: number;
}

export default function LineChartWithTrend({ data, actualLabel = 'Actual', trendLabel = 'Trend', anomalyThreshold = 0.75 }: Props) {
  const chartData = data
    .filter(d => d.actual !== null || d.trend !== null)
    .map(d => ({
      year: d.year,
      [actualLabel]: d.actual,
      [trendLabel]: d.trend,
      isAnomaly: d.anomaly && d.anomaly >= anomalyThreshold,
    }));

  return (
    <ResponsiveContainer width="100%" height={400}>
      <LineChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="year" />
        <YAxis />
        <Tooltip />
        <Legend />
        <Line type="monotone" dataKey={actualLabel} stroke="#8884d8" dot={{ r: 3 }} />
        <Line type="monotone" dataKey={trendLabel} stroke="#82ca9d" strokeDasharray="5 5" dot={false} />
        {chartData.filter(d => d.isAnomaly).map((point, idx) => (
          <ReferenceLine key={`anomaly-${idx}`} x={point.year} stroke="red" strokeDasharray="3 3" label="Anomaly" />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}