'use client';
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { useMemo } from 'react';

interface Props {
  data: { cluster_id: number; count: number }[];
  groupedCountries?: Record<number, string[]>;
}

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#A28DFF'];

const CustomTooltip = ({ active, payload, groupedCountries }: any) => {
  if (active && payload && payload.length) {
    const clusterId = payload[0].payload.cluster_id || parseInt(payload[0].name.replace('Cluster ', ''));
    const countries = groupedCountries?.[clusterId] || [];
    return (
      <div className="bg-white p-3 rounded shadow border border-gray-200 text-sm min-w-[180px]">
        <p className="font-semibold mb-2">{payload[0].name} ({payload[0].value} countries)</p>
        <div className="max-h-28 overflow-y-auto space-y-1 pr-1 custom-scrollbar">
          {countries.slice(0, 5).map((code: string) => (
            <div key={code} className="text-gray-600 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-gray-400" /> {code}
            </div>
          ))}
          {countries.length > 5 && (
            <div className="text-gray-400 text-xs mt-1 italic">...và {countries.length - 5} quốc gia khác</div>
          )}
        </div>
      </div>
    );
  }
  return null;
};

export default function ClusterPieChart({ data, groupedCountries }: Props) {
  const chartData = useMemo(() =>
    data.map(item => ({ name: `Cluster ${item.cluster_id}`, value: item.count, cluster_id: item.cluster_id })),
    [data]
  );

  return (
    <ResponsiveContainer width="100%" height={300}>
      <PieChart>
        <Pie
          data={chartData}
          cx="50%" cy="50%"
          labelLine={false}
          label={({ name, percent }) => `${name}: ${((percent ?? 0) * 100).toFixed(0)}%`}
          outerRadius={80} fill="#8884d8" dataKey="value"
        >
          {chartData.map((_entry, index) => (
            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
          ))}
        </Pie>
        <Tooltip content={(props) => <CustomTooltip {...props} groupedCountries={groupedCountries} />} />
        <Legend />
      </PieChart>
    </ResponsiveContainer>
  );
}