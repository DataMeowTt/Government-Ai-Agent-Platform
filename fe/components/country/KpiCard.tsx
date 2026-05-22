import { LucideIcon, ArrowUpRight, ArrowDownRight, Minus } from 'lucide-react';
import { LineChart, Line, ResponsiveContainer } from 'recharts';
import { formatValue } from '@/lib/utils/format';

interface KpiCardProps {
  icon: LucideIcon;
  label: string;
  value: number | null | undefined;
  unit: string;
  trendDirection: 'up' | 'down' | 'flat' | null;
  trendValue: string | null;
  sparklineData: number[];
}

export default function KpiCard({ icon: Icon, label, value, unit, trendDirection, trendValue, sparklineData }: KpiCardProps) {
  const TrendIcon = trendDirection === 'up' ? ArrowUpRight : trendDirection === 'down' ? ArrowDownRight : Minus;
  const trendColor = trendDirection === 'up' ? 'text-emerald-600' : trendDirection === 'down' ? 'text-rose-600' : 'text-gray-500';

  return (
    <div className="h-[120px] bg-white rounded-md border border-gray-200 p-4 flex flex-col justify-between transition-shadow hover:shadow-sm">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="p-2 bg-slate-100 rounded-md text-slate-600"><Icon className="w-4 h-4" /></div>
          <span className="text-sm font-medium text-gray-600">{label}</span>
        </div>
        {trendDirection && trendValue && (
          <div className={`flex items-center gap-1 text-xs font-medium ${trendColor}`}>
            <TrendIcon className="w-3 h-3" /> {trendValue}
          </div>
        )}
      </div>
      <div className="flex items-end justify-between mt-2">
        <span className="text-2xl font-bold text-gray-900">{formatValue(value)}{unit ? ` ${unit}` : ''}</span>
        <div className="w-24 h-8">
          {sparklineData.length > 1 ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={sparklineData.map((v, i) => ({ v, i }))}>
                <Line type="monotone" dataKey="v" stroke="#3b82f6" strokeWidth={2} dot={false} connectNulls={false} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-1 w-full bg-gray-100 rounded" />
          )}
        </div>
      </div>
    </div>
  );
}