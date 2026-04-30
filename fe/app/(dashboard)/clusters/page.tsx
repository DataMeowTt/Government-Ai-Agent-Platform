'use client';
import { useUrlState } from '@/lib/hooks/useUrlState';
import { useClusters } from '@/lib/hooks/useClusters';
import { useDataState } from '@/lib/hooks/useDataState';
import dynamic from 'next/dynamic';
import { ChartSkeleton, CardSkeleton } from '@/components/ui/Skeletons';
import { useMemo } from 'react';
import { Layers, ArrowUpRight, AlertCircle } from 'lucide-react';
import Link from 'next/link';

const ClusterPieChart = dynamic(() => import('@/components/charts/PieChart'), {
  ssr: false,
  loading: () => <ChartSkeleton />
});

export default function ClustersPage() {
  const [year, setYear] = useUrlState<number>('year', 2022);
  const { data: clusters, isLoading, isEmpty, isError, error } = useDataState(useClusters(year));

  const { clusterCounts, grouped } = useMemo(() => {
    const counts: Record<number, number> = {};
    const grp: Record<number, string[]> = {};
    if (!isEmpty && clusters) {
      clusters.forEach(item => {
        const id = item.cluster_id;
        counts[id] = (counts[id] || 0) + 1;
        if (!grp[id]) grp[id] = [];
        grp[id].push(item.country_code);
      });
    }
    return { clusterCounts: counts, grouped: grp };
  }, [clusters, isEmpty]);

  const pieData = Object.entries(clusterCounts).map(([id, count]) => ({
    cluster_id: parseInt(id),
    count,
  }));

  if (isError) return <div className="p-4 bg-red-50 text-red-700 rounded border border-red-200">Lỗi: {error?.message}</div>;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-indigo-50 rounded-md text-indigo-600">
            <Layers className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Phân nhóm Cấu trúc Kinh tế</h1>
            <p className="text-sm text-gray-500">Phương pháp: K-Means Clustering (5 nhóm đặc trưng)</p>
          </div>
        </div>
        <div className="flex items-center gap-3 bg-white px-4 py-2 rounded-md border border-gray-200 shadow-sm">
          <span className="text-sm font-medium text-gray-700">Năm dữ liệu:</span>
          <select
            value={year}
            onChange={(e) => setYear(parseInt(e.target.value))}
            className="text-sm font-semibold text-gray-900 bg-transparent border-none focus:ring-0 cursor-pointer"
          >
            {[2000, 2010, 2015, 2020, 2022].map(y => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Chart Area (2 cols) */}
        <div className="lg:col-span-2 bg-white rounded-md border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-lg font-semibold text-gray-900">Biểu đồ Phân bố</h2>
            {isLoading && <span className="text-xs text-gray-400 animate-pulse">Đang tải dữ liệu...</span>}
          </div>
          {isLoading ? (
            <ChartSkeleton />
          ) : isEmpty ? (
            <div className="h-[300px] flex flex-col items-center justify-center text-gray-500">
              <AlertCircle className="w-12 h-12 text-gray-300 mb-4" />
              <p className="text-sm">Chưa có dữ liệu phân nhóm cho năm {year}.</p>
            </div>
          ) : (
            <ClusterPieChart data={pieData} groupedCountries={grouped} />
          )}
        </div>

        {/* Member List (1 col) */}
        <div className="lg:col-span-1 bg-white rounded-md border border-gray-200 p-6 flex flex-col h-full">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Hồ sơ Cụm & Thành viên</h2>
          <div className="flex-1 overflow-y-auto pr-2 space-y-4 custom-scrollbar">
            {isLoading ? (
              <>
                <CardSkeleton className="h-32" />
                <CardSkeleton className="h-32" />
              </>
            ) : isEmpty ? (
              <div className="text-center text-sm text-gray-500 py-8">Không có dữ liệu.</div>
            ) : (
              Object.keys(grouped).sort((a, b) => parseInt(a) - parseInt(b)).map(id => (
                <div key={id} className="p-4 border border-gray-100 rounded-md bg-gray-50/50 hover:bg-gray-50 transition-colors">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="font-medium text-indigo-700">Cụm {id}</h3>
                    <span className="text-xs font-medium px-2 py-1 bg-white rounded-full border border-gray-200 text-gray-600">
                      {grouped[parseInt(id)].length} quốc gia
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {grouped[parseInt(id)].map(code => (
                      <Link
                        key={code}
                        href={`/countries/${code}`}
                        className="flex items-center gap-1 px-2 py-1 bg-white border border-gray-200 rounded text-xs font-medium text-gray-700 hover:text-blue-600 hover:border-blue-300 transition-colors"
                        title={`Xem chi tiết ${code}`}
                      >
                        {code} <ArrowUpRight className="w-3 h-3" />
                      </Link>
                    ))}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}