import { Globe2, MapPin, Layers, ShieldCheck } from 'lucide-react';
import { cn } from '@/lib/utils/cn';

interface CountryInfoPanelProps {
  code: string;
  region?: string | null;
  incomeGroup?: string | null;
  dataCompleteness?: number | null;
  className?: string;
}

export default function CountryInfoPanel({ code, region, incomeGroup, dataCompleteness, className }: CountryInfoPanelProps) {
  const qualityColor = dataCompleteness != null ? (dataCompleteness > 80 ? 'bg-emerald-500' : dataCompleteness > 50 ? 'bg-amber-500' : 'bg-rose-500') : 'bg-gray-300';
  const qualityWidth = dataCompleteness != null ? `${Math.min(Math.max(dataCompleteness, 0), 100)}%` : '0%';

  return (
    <div className={cn('bg-white rounded-md border border-slate-200 p-5 space-y-4', className)}>
      <h3 className="text-base font-semibold text-slate-900 border-b border-slate-100 pb-3">Thông tin Quốc gia</h3>
      <div className="space-y-3">
        <div className="flex items-center gap-3 text-sm">
          <Globe2 className="w-4 h-4 text-slate-400" />
          <span className="text-slate-600">Mã:</span>
          <span className="font-mono font-medium text-slate-900">{code}</span>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <MapPin className="w-4 h-4 text-slate-400" />
          <span className="text-slate-600">Khu vực:</span>
          <span className="font-medium text-slate-900">{region || 'Chưa xác định'}</span>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <Layers className="w-4 h-4 text-slate-400" />
          <span className="text-slate-600">Nhóm thu nhập:</span>
          <span className="font-medium text-slate-900">{incomeGroup || 'Chưa phân loại'}</span>
        </div>
        {dataCompleteness != null && (
          <div className="pt-2 border-t border-slate-100">
            <div className="flex items-center justify-between text-sm mb-1.5">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-slate-400" />
                <span className="text-slate-600">Chất lượng dữ liệu</span>
              </div>
              <span className="font-semibold text-slate-900">{dataCompleteness}%</span>
            </div>
            <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
              <div className={cn('h-full rounded-full transition-all duration-500', qualityColor)} style={{ width: qualityWidth }} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}