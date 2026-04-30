'use client';
import { useCountries } from '@/lib/hooks/useCountries';
import { useClusters } from '@/lib/hooks/useClusters';
import { useAnomalies } from '@/lib/hooks/useAnomalies';
import MetricCard from '@/components/ui/MetricCard';
import ContextPanel from '@/components/ui/ContextPanel';
import { Globe2, Layers, AlertTriangle, ShieldCheck, BarChart3, Search } from 'lucide-react';
import Link from 'next/link';

export default function DashboardPage() {
  const { data: countries, isLoading: l1 } = useCountries();
  const { data: clusters, isLoading: l2 } = useClusters(2022);
  const { data: anomalies, isLoading: l3 } = useAnomalies({ limit: 50 });

  const totalCountries = countries?.length || 0;
  const clusterCount = clusters ? new Set(clusters.map(c => c.cluster_id)).size : 0;
  const totalAnomalies = anomalies?.length || 0;

  const contextItems = [
    { icon: Globe2, label: 'Quốc gia theo dõi', value: l1 ? undefined : `${totalCountries}` },
    { icon: Layers, label: 'Nhóm cấu trúc (2022)', value: l2 ? undefined : `${clusterCount}` },
    { icon: AlertTriangle, label: 'Cảnh báo hiện tại', value: l3 ? undefined : `${totalAnomalies}` },
  ];

  return (
    <div className="space-y-8">
      {/* Header Dashboard */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <h1 className="text-2xl font-bold text-gray-900">Bảng Điều Khiển Tổng Quan</h1>
        <div className="flex items-center gap-2 text-xs font-medium text-gray-500 bg-white px-3 py-1.5 rounded-full border border-gray-200 shadow-sm">
          <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
          Dữ liệu đồng bộ: 2022
        </div>
      </div>

      {/* Grid chính: Metrics + Context Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* 3 Metrics Cards */}
        <div className="lg:col-span-8 grid grid-cols-1 md:grid-cols-3 gap-6">
          <MetricCard
            icon={Globe2}
            title="Tổng Quốc gia"
            value={l1 ? '...' : totalCountries || '--'}
            isLoading={l1}
            action={{ label: 'Xem danh sách', href: '/countries' }}
          />
          <MetricCard
            icon={Layers}
            title="Nhóm Cấu trúc"
            value={l2 ? '...' : clusterCount || '--'}
            isLoading={l2}
            action={{ label: 'Xem phân bố', href: '/clusters' }}
          />
          <MetricCard
            icon={AlertTriangle}
            title="Bất thường phát hiện"
            value={l3 ? '...' : totalAnomalies || '--'}
            trend={!l3 && totalAnomalies > 0 ? { value: 'Cần chú ý', direction: 'up' } : undefined}
            isLoading={l3}
            action={{ label: 'Kiểm tra chi tiết', href: '/anomalies' }}
          />
        </div>

        {/* Context Panel */}
        <div className="lg:col-span-4">
          <ContextPanel
            title="Trạng thái Hệ thống"
            items={contextItems}
            actions={[
              { label: 'Làm mới dữ liệu', onClick: () => window.location.reload(), variant: 'secondary' },
            ]}
          />
        </div>
      </div>

      {/* Task Navigation Zone */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Nhiệm vụ Phân tích</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <Link href="/anomalies" className="group flex flex-col justify-between p-6 bg-white rounded-md border border-gray-200 hover:border-blue-300 hover:shadow-md transition-all">
            <div className="flex items-start gap-4">
              <div className="p-2.5 bg-blue-50 rounded-lg text-blue-600 group-hover:bg-blue-100 transition-colors">
                <ShieldCheck className="w-6 h-6" />
              </div>
              <div>
                <h3 className="font-semibold text-gray-900 group-hover:text-blue-700 transition-colors">Giám sát Rủi ro</h3>
                <p className="text-sm text-gray-500 mt-1">Phát hiện các dấu hiệu bất thường về nợ công, tăng trưởng và tỷ giá.</p>
              </div>
            </div>
            <div className="mt-4 text-sm font-medium text-blue-600 flex items-center gap-1">
              Truy cập ngay <span className="transition-transform group-hover:translate-x-1">→</span>
            </div>
          </Link>

          <Link href="/compare" className="group flex flex-col justify-between p-6 bg-white rounded-md border border-gray-200 hover:border-blue-300 hover:shadow-md transition-all">
            <div className="flex items-start gap-4">
              <div className="p-2.5 bg-purple-50 rounded-lg text-purple-600 group-hover:bg-purple-100 transition-colors">
                <BarChart3 className="w-6 h-6" />
              </div>
              <div>
                <h3 className="font-semibold text-gray-900 group-hover:text-purple-700 transition-colors">So sánh Đa chiều</h3>
                <p className="text-sm text-gray-500 mt-1">Đối sánh chỉ số vĩ mô giữa các quốc gia theo thời gian thực.</p>
              </div>
            </div>
            <div className="mt-4 text-sm font-medium text-purple-600 flex items-center gap-1">
              So sánh ngay <span className="transition-transform group-hover:translate-x-1">→</span>
            </div>
          </Link>
          
          <Link href="/chat" className="group flex flex-col justify-between p-6 bg-white rounded-md border border-gray-200 hover:border-blue-300 hover:shadow-md transition-all">
            <div className="flex items-start gap-4">
              <div className="p-2.5 bg-green-50 rounded-lg text-green-600 group-hover:bg-green-100 transition-colors">
                <Search className="w-6 h-6" />
              </div>
              <div>
                <h3 className="font-semibold text-gray-900 group-hover:text-green-700 transition-colors">Trợ lý AI</h3>
                <p className="text-sm text-gray-500 mt-1">Hỏi đáp thông minh về dữ liệu kinh tế vĩ mô (Đang phát triển).</p>
              </div>
            </div>
            <div className="mt-4 text-sm font-medium text-green-600 flex items-center gap-1">
              Khám phá <span className="transition-transform group-hover:translate-x-1">→</span>
            </div>
          </Link>
        </div>
      </div>
    </div>
  );
}