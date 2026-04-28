'use client';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

interface Props {
  data: Record<string, { year: number; value: number }[]>;
  indicatorName: string;
}

const COLORS = ['#8884d8', '#82ca9d', '#ffc658', '#ff7300', '#0088fe'];

export default function CompareLineChart({ data, indicatorName }: Props) {
  const allYears = new Set<number>();
  Object.values(data).forEach(countryData => {
    countryData.forEach(point => allYears.add(point.year));
  });
  const years = Array.from(allYears).sort();

  const chartData = years.map(year => {
    const point: any = { year };
    Object.entries(data).forEach(([countryCode, countryData]) => {
      const found = countryData.find(d => d.year === year);
      point[countryCode] = found?.value ?? null;
    });
    return point;
  });

  return (
    <ResponsiveContainer width="100%" height={400}>
      <LineChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="year" />
        <YAxis />
        <Tooltip />
        <Legend />
        {Object.keys(data).map((countryCode, idx) => (
          <Line
            key={countryCode}
            type="monotone"
            dataKey={countryCode}
            stroke={COLORS[idx % COLORS.length]}
            name={countryCode}
            dot={{ r: 3 }}
            connectNulls
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}