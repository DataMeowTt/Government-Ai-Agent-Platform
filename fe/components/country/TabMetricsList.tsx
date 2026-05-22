import { cn } from '@/lib/utils/cn';

interface MetricItem {
  label: string;
  value: string;
  status?: 'ok' | 'warning' | 'error';
}

interface TabMetricsListProps {
  metrics: MetricItem[];
  className?: string;
}

export default function TabMetricsList({ metrics, className }: TabMetricsListProps) {
  if (!metrics.length) return null;
  return (
    <div className={cn('bg-slate-50 rounded-md border border-slate-200 p-4 h-[320px] overflow-y-auto', className)}>
      <h4 className="text-sm font-semibold text-slate-700 mb-3">Chỉ số bổ trợ</h4>
      <div className="space-y-3">
        {metrics.map((m, i) => (
          <div key={i} className="flex items-center justify-between border-b border-slate-200 pb-2 last:border-0 last:pb-0">
            <span className="text-xs text-slate-500">{m.label}</span>
            <span className={cn(
              'text-xs font-medium px-1.5 py-0.5 rounded',
              m.status === 'ok' ? 'text-emerald-700 bg-emerald-100' :
              m.status === 'warning' ? 'text-amber-700 bg-amber-100' :
              m.status === 'error' ? 'text-rose-700 bg-rose-100' :
              'text-slate-700 bg-slate-200'
            )}>{m.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
