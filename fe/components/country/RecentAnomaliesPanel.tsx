import { AlertCircle, AlertTriangle, CheckCircle } from 'lucide-react';
import { cn } from '@/lib/utils/cn';
import { formatValue } from '@/lib/utils/format';

interface Anomaly { year: number; indicator: string; score: number; }
interface RecentAnomaliesPanelProps { anomalies: Anomaly[]; className?: string; }

const INDICATOR_MAP: Record<string, string> = {
  rGDP_growth_YoY: 'Tăng trưởng', govdebt_GDP: 'Nợ công', inflation_cpi: 'Lạm phát',
  actual_reer_deviation: 'REER', unemployment_total: 'Thất nghiệp', poverty_headcount: 'Nghèo đói'
};

export default function RecentAnomaliesPanel({ anomalies, className }: RecentAnomaliesPanelProps) {
  const sorted = [...anomalies].sort((a, b) => b.score - a.score).slice(0, 3);
  if (!sorted.length) {
    return (
      <div className={cn('bg-white rounded-md border border-slate-200 p-5', className)}>
        <h3 className="text-base font-semibold text-slate-900 mb-3 border-b border-slate-100 pb-3">Cảnh báo gần đây</h3>
        <div className="flex flex-col items-center justify-center py-4 text-slate-500 text-sm">
          <CheckCircle className="w-6 h-6 text-emerald-500 mb-2" />
          Không có cảnh báo bất thường
        </div>
      </div>
    );
  }
  return (
    <div className={cn('bg-white rounded-md border border-slate-200 p-5', className)}>
      <h3 className="text-base font-semibold text-slate-900 mb-3 border-b border-slate-100 pb-3">Cảnh báo gần đây</h3>
      <div className="space-y-3">
        {sorted.map((a, i) => (
          <div key={i} className="flex items-start gap-3 p-2 rounded-md bg-slate-50">
            <div className="mt-0.5">
              {a.score >= 0.9 ? <AlertTriangle className="w-4 h-4 text-rose-500" /> : <AlertCircle className="w-4 h-4 text-amber-500" />}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-800 truncate">{INDICATOR_MAP[a.indicator] || a.indicator}</span>
                <span className="text-xs font-mono text-slate-500">{a.year}</span>
              </div>
              <div className="mt-1 flex items-center justify-between">
                <span className="text-xs text-slate-500">Điểm bất thường</span>
                <span className={cn('text-xs font-medium px-1.5 py-0.5 rounded', a.score >= 0.9 ? 'bg-rose-100 text-rose-700' : 'bg-amber-100 text-amber-700')}>{formatValue(a.score, 3)}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
