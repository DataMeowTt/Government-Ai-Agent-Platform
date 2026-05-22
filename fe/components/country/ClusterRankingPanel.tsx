import { Trophy, Hash, TrendingUp } from 'lucide-react';
import { cn } from '@/lib/utils/cn';

const CLUSTER_LABELS: Record<number, string> = {
  0: 'Nông nghiệp chủ đạo', 1: 'Công nghiệp hóa nhanh', 2: 'Dịch vụ & Thu nhập cao',
  3: 'Phụ thuộc tài nguyên', 4: 'Kinh tế mở & Chuyên môn hóa'
};

interface ClusterRankingPanelProps {
  clusterId?: number | null;
  clusterLabel?: string;
  className?: string;
}

export default function ClusterRankingPanel({ clusterId, clusterLabel, className }: ClusterRankingPanelProps) {
  const label = clusterLabel || (clusterId != null ? CLUSTER_LABELS[clusterId] : 'Đang phân tích...');
  if (clusterId == null) return null;
  return (
    <div className={cn('bg-white rounded-md border border-slate-200 p-5 space-y-4', className)}>
      <h3 className="text-base font-semibold text-slate-900 border-b border-slate-100 pb-3">Phân cụm & Xếp hạng</h3>
      <div className="space-y-3">
        <div className="flex items-center gap-3 text-sm">
          <Hash className="w-4 h-4 text-slate-400" />
          <span className="text-slate-600">Cụm ID:</span>
          <span className="font-medium text-slate-900">#{clusterId}</span>
        </div>
        <div className="flex items-start gap-3 text-sm">
          <Trophy className="w-4 h-4 text-slate-400 mt-0.5" />
          <div>
            <span className="text-slate-600 block">Đặc trưng cụm</span>
            <span className="font-medium text-slate-900">{label}</span>
          </div>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <TrendingUp className="w-4 h-4 text-slate-400" />
          <span className="text-slate-600">So sánh cụm</span>
          <span className="font-medium text-slate-900">Đang cập nhật</span>
        </div>
      </div>
    </div>
  );
}
