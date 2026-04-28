'use client';
import { useParams } from 'next/navigation';
import { useCountryAnalytics } from '@/lib/hooks/useCountries';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Scatter,
} from 'recharts';

export default function CountryDetailPage() {
  const { code } = useParams();
  const { data, isLoading, error } = useCountryAnalytics(code as string);

  if (isLoading) return <div>Loading country data...</div>;
  if (error) return <div>Error: {error.message}</div>;
  if (!data || data.length === 0) return <div>No data for this country.</div>;

  const chartData = data.map((item: any) => ({
    year: item.year,
    actual: item.actual_growth,
    trend: item.trend_growth,
    anomaly: item.anomaly_growth > 0.75 ? item.actual_growth : null,
  }));

  return (
    <div>
      <h1 className="text-2xl font-bold mb-2">Country: {code}</h1>
      <div className="bg-white p-4 rounded shadow mb-6">
        <h2 className="text-lg font-semibold mb-2">Growth Dynamics</h2>
        <ResponsiveContainer width="100%" height={400}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="year" />
            <YAxis />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="actual" stroke="#8884d8" name="Actual GDP Growth" />
            <Line type="monotone" dataKey="trend" stroke="#82ca9d" name="Trend" strokeDasharray="5 5" />
            <Scatter dataKey="anomaly" fill="#ff7300" name="Anomaly (score > 0.75)" />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}