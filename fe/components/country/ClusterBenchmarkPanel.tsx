'use client';
import { useClusterBenchmark } from '@/lib/hooks/useCountries';
import { BarChart4, TrendingUp } from 'lucide-react';
import { cn } from '@/lib/utils/cn';

interface ClusterBenchmarkPanelProps {
  countryCode: string;
  clusterId?: number | null;
  year?: number;
  activeIndicator: string;
  className?: string;
}

export default function ClusterBenchmarkPanel({ countryCode, clusterId, year, activeIndicator, className }: ClusterBenchmarkPanelProps) {
  const { data, isLoading } = useClusterBenchmark(countryCode, activeIndicator, year);
  if (!clusterId || isLoading) return null;
  if (!data) return <div className="p-4 text-center text-xs text-slate-400 border border-dashed border-slate-200 rounded-md">Không hỗ trợ benchmark cho chỉ số này.</div>;

  const diff = (data.members.find((m: any) => m.country_code === countryCode)?.value ?? 0) - data.average;
  const isBetter = diff > 0;

  return (
    <div className={cn('bg-white rounded-md border border-slate-200 p-5 space-y-4', className)}>
      <h3 className="text-base font-semibold text-slate-900 border-b border-slate-100 pb-3">So sánh Cụm #{clusterId}</h3>
      <div className="flex items-center gap-3">
        <div className={cn('p-2 rounded-md', isBetter ? 'bg-emerald-50 text-emerald-600' : 'bg-rose-50 text-rose-600')}>
          <TrendingUp className="w-4 h-4" />
        </div>
        <div>
          <p className="text-xs text-slate-500">Trung bình cụm</p>
          <p className="text-sm font-semibold text-slate-900">{data.average.toFixed(2)}%</p>
        </div>
        <div className="ml-auto text-right">
          <p className="text-xs text-slate-500">Chênh lệch</p>
          <p className={cn('text-sm font-semibold', isBetter ? 'text-emerald-600' : 'text-rose-600')}>
            {diff > 0 ? '+' : ''}{diff.toFixed(2)}%
          </p>
        </div>
      </div>
      <div className="bg-slate-50 rounded-md p-3 border border-slate-100">
        <div className="flex items-center gap-2 text-xs text-slate-500 mb-2">
          <BarChart4 className="w-3 h-3" /> Thành viên trong cụm ({data.members.length})
        </div>
        <div className="flex flex-wrap gap-1">
          {data.members.slice(0, 6).map((m: any) => (
            <span key={m.country_code} className={cn('px-2 py-0.5 rounded text-xs font-medium border', m.country_code === countryCode ? 'bg-blue-100 border-blue-300 text-blue-700' : 'bg-white border-slate-200 text-slate-600')}>
              {m.country_code}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}