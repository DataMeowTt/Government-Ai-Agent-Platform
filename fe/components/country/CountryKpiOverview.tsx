import { TrendingUp, Landmark, Coins, Users } from 'lucide-react';
import KpiCard from './KpiCard';
import { CountryAnalyticsRow } from '@/lib/types';
import { useMemo } from 'react';

interface CountryKpiOverviewProps {
  data: CountryAnalyticsRow[];
}

export default function CountryKpiOverview({ data }: CountryKpiOverviewProps) {
  const latest = useMemo(() => (data.length > 0 ? data[data.length - 1] : null), [data]);
  const prev = useMemo(() => (data.length > 1 ? data[data.length - 2] : null), [data]);

  const calcTrend = (curr: number | null | undefined, prevVal: number | null | undefined): { dir: 'up' | 'down' | 'flat' | null; val: string | null } => {
    if (curr == null || prevVal == null || prevVal === 0) return { dir: null, val: null };
    const diff = curr - prevVal;
    const dir: 'up' | 'down' | 'flat' = diff > 0.1 ? 'up' : diff < -0.1 ? 'down' : 'flat';
    return { dir, val: `${Math.abs(diff).toFixed(1)}%` };
  };

  const getSparklineArray = (key: keyof CountryAnalyticsRow, count = 5) =>
    useMemo(() => data.slice(-count).map(d => (d[key] != null ? Number(d[key]) : 0)), [data, key, count]);

  const growthTrend = useMemo(() => calcTrend(latest?.actual_growth, prev?.actual_growth), [latest, prev]);
  const debtTrend = useMemo(() => calcTrend(latest?.actual_debt, prev?.actual_debt), [latest, prev]);
  const inflationTrend = useMemo(() => calcTrend(latest?.actual_inflation, prev?.actual_inflation), [latest, prev]);
  const unemploymentTrend = useMemo(() => calcTrend(latest?.actual_unemployment, prev?.actual_unemployment), [latest, prev]);

  const growthSpark = getSparklineArray('actual_growth');
  const debtSpark = getSparklineArray('actual_debt');
  const inflationSpark = getSparklineArray('actual_inflation');
  const unemploymentSpark = getSparklineArray('actual_unemployment');

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      <KpiCard icon={TrendingUp} label="Tăng trưởng GDP" value={latest?.actual_growth} unit="%" trendDirection={growthTrend.dir} trendValue={growthTrend.val} sparklineData={growthSpark} />
      <KpiCard icon={Landmark} label="Nợ công" value={latest?.actual_debt} unit="%" trendDirection={debtTrend.dir} trendValue={debtTrend.val} sparklineData={debtSpark} />
      <KpiCard icon={Coins} label="Lạm phát CPI" value={latest?.actual_inflation} unit="%" trendDirection={inflationTrend.dir} trendValue={inflationTrend.val} sparklineData={inflationSpark} />
      <KpiCard icon={Users} label="Thất nghiệp" value={latest?.actual_unemployment} unit="%" trendDirection={unemploymentTrend.dir} trendValue={unemploymentTrend.val} sparklineData={unemploymentSpark} />
    </div>
  );
}