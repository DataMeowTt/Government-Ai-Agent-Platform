'use client';
import React, { useMemo } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

interface Props {
  data: Record<string, { year: number; value: number | null }[]>;
  indicatorName: string;
}

const getStableColor = (str: string) => {
  let hash = 0;
  for (let i = 0; i < str.length; i++) hash = str.charCodeAt(i) + ((hash << 5) - hash);
  const c = (hash & 0x00ffffff).toString(16).toUpperCase();
  return '#' + '00000'.substring(0, 6 - c.length) + c;
};

const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-white p-3 rounded shadow border border-gray-200 text-sm min-w-[200px]">
        <p className="font-semibold mb-2 text-gray-800">Year: {label}</p>
        {payload.map((entry: any, idx: number) => {
          const isMissing = entry.value == null;
          return (
            <div key={idx} className="flex items-center gap-2 mb-1.5 last:mb-0">
              <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: entry.color }} />
              <span className="font-medium text-gray-700">{entry.name}:</span>
              {isMissing ? (
                <span className="text-yellow-600 flex items-center gap-1 text-xs font-medium">
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
                  Missing Data
                </span>
              ) : (
                <span className="text-gray-600">{Number(entry.value).toFixed(2)}</span>
              )}
            </div>
          );
        })}
      </div>
    );
  }
  return null;
};

const CompareLineChart = React.memo(function CompareLineChart({ data, indicatorName }: Props) {
  const countries = Object.keys(data);

  if (!countries.length) {
    return <div className="h-64 flex items-center justify-center bg-gray-50 rounded text-gray-500">Chưa có dữ liệu để hiển thị</div>;
  }

  const allYears = useMemo(() => {
    const years = new Set<number>();
    Object.values(data).forEach(arr => arr.forEach(p => years.add(p.year)));
    return Array.from(years).sort((a, b) => a - b);
  }, [data]);

  const chartData = useMemo(() => allYears.map(year => {
    const point: Record<string, number | null> = { year };
    countries.forEach(code => {
      const found = data[code].find(p => p.year === year);
      point[code] = found?.value ?? null;
    });
    return point;
  }), [allYears, data, countries]);

  return (
    <div>
      <h3 className="text-sm font-medium text-gray-600 mb-2">{indicatorName}</h3>
      <ResponsiveContainer width="100%" height={350}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="year" tick={{ fontSize: 12 }} />
          <YAxis tick={{ fontSize: 12 }} />
          <Tooltip content={<CustomTooltip />} />
          <Legend />
          {countries.map((code) => (
            <Line
              key={code}
              type="monotone"
              dataKey={code}
              stroke={getStableColor(code)}
              name={code}
              dot={{ r: 3 }}
              connectNulls={false}
              activeDot={{ r: 5 }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
});

export default CompareLineChart;