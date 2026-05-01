import { TrendingUp, Landmark, Coins, Users } from 'lucide-react';
import KpiCard from './KpiCard';
import { CountryAnalyticsRow } from '@/lib/types';

interface CountryKpiOverviewProps {
  data: CountryAnalyticsRow[];
}

export default function CountryKpiOverview({ data }: CountryKpiOverviewProps) {
  const latest = data.length > 0 ? data[data.length - 1] : null;
  const prev = data.length > 1 ? data[data.length - 2] : null;

  const calcTrend = (curr: number | null | undefined, prevVal: number | null | undefined): { dir: 'up' | 'down' | 'flat' | null; val: string | null } => {
    if (curr == null || prevVal == null || prevVal === 0) return { dir: null, val: null };
    const diff = curr - prevVal;
    const dir: 'up' | 'down' | 'flat' = diff > 0.1 ? 'up' : diff < -0.1 ? 'down' : 'flat';
    return { dir, val: `${Math.abs(diff).toFixed(1)}%` };
  };

  const getSparkline = (key: keyof CountryAnalyticsRow, count = 5) => {
    return data.slice(-count).map(d => d[key] != null ? Number(d[key]) : 0);
  };

  const growthTrend = calcTrend(latest?.actual_growth, prev?.actual_growth);
  const debtTrend = calcTrend(latest?.actual_debt, prev?.actual_debt);
  const inflationTrend = calcTrend(latest?.actual_inflation, prev?.actual_inflation);
  const unemploymentTrend = calcTrend(latest?.actual_unemployment, prev?.actual_unemployment);

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      <KpiCard icon={TrendingUp} label="Tăng trưởng GDP" value={latest?.actual_growth} unit="%" trendDirection={growthTrend.dir} trendValue={growthTrend.val} sparklineData={getSparkline('actual_growth')} />
      <KpiCard icon={Landmark} label="Nợ công" value={latest?.actual_debt} unit="%" trendDirection={debtTrend.dir} trendValue={debtTrend.val} sparklineData={getSparkline('actual_debt')} />
      <KpiCard icon={Coins} label="Lạm phát CPI" value={latest?.actual_inflation} unit="%" trendDirection={inflationTrend.dir} trendValue={inflationTrend.val} sparklineData={getSparkline('actual_inflation')} />
      <KpiCard icon={Users} label="Thất nghiệp" value={latest?.actual_unemployment} unit="%" trendDirection={unemploymentTrend.dir} trendValue={unemploymentTrend.val} sparklineData={getSparkline('actual_unemployment')} />
    </div>
  );
}