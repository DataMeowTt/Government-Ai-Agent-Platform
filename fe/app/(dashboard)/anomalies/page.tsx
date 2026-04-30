'use client';
import { useUrlState } from '@/lib/hooks/useUrlState';
import { useDebounce } from '@/lib/hooks/useDebounce';
import { useAnomalies } from '@/lib/hooks/useAnomalies';
import { useCountries } from '@/lib/hooks/useCountries';
import AnomaliesTable from '@/components/tables/AnomaliesTable';
import Pagination from '@/components/ui/Pagination';
import { TableSkeleton } from '@/components/ui/Skeletons';
import { Search, RotateCcw, Filter } from 'lucide-react';

export default function AnomaliesPage() {
  const [country, setCountry] = useUrlState<string>('country', '');
  const [rawThreshold, setThreshold] = useUrlState<number>('threshold', 0.75);
  const [page, setPage] = useUrlState<number>('page', 1);
  const threshold = useDebounce(rawThreshold, 300);

  const { data: countries, isLoading: loadingCountries } = useCountries();
  const { data, total, isLoading, isEmpty, isError, error } = useAnomalies({ 
    country: country || undefined, 
    threshold, 
    limit: 200 
  });

  const ITEMS_PER_PAGE = 15;
  const totalPages = Math.ceil((total || 0) / ITEMS_PER_PAGE);
  const paginatedData = data?.slice((page - 1) * ITEMS_PER_PAGE, page * ITEMS_PER_PAGE) || [];

  const handleClearFilters = () => {
    setCountry('');
    setThreshold(0.75);
    setPage(1);
  };

  if (loadingCountries) return <TableSkeleton rows={1} />;
  if (isError) return <div className="p-4 bg-red-50 text-red-700 rounded border border-red-200">Lỗi: {error?.message}</div>;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <h1 className="text-2xl font-bold text-gray-900">Giám sát Bất thường</h1>
        <div className="flex items-center gap-2 text-sm text-gray-500 bg-white px-3 py-1.5 rounded-full border border-gray-200 shadow-sm">
          <span className="font-medium text-gray-900">{total || 0}</span> kết quả
          {total && total >= 200 && <span className="text-amber-600">(Tối đa 200)</span>}
        </div>
      </div>

      {/* Filter Panel */}
      <div className="bg-white p-6 rounded-md border border-gray-200 shadow-sm space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 items-end">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">Quốc gia</label>
            <select
              className="w-full h-10 px-3 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
              value={country}
              onChange={(e) => setCountry(e.target.value)}
            >
              <option value="">Tất cả</option>
              {countries?.map((c) => (
                <option key={c.country_code} value={c.country_code}>{c.country_name}</option>
              ))}
            </select>
          </div>
          <div className="lg:col-span-2">
            <div className="flex justify-between mb-1.5">
              <label className="block text-sm font-medium text-gray-700">Ngưỡng Anomaly</label>
              <span className="text-xs font-mono text-blue-600 bg-blue-50 px-2 py-0.5 rounded">{rawThreshold.toFixed(2)}</span>
            </div>
            <input
              type="range" min="0" max="1" step="0.01" value={rawThreshold}
              onChange={(e) => setThreshold(parseFloat(e.target.value))}
              className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
            />
            <div className="flex justify-between text-xs text-gray-400 mt-1"><span>0.5 (Thấp)</span><span>1.0 (Cao)</span></div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setPage(1)}
              disabled={isLoading}
              className="flex-1 h-10 px-4 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 disabled:opacity-50 flex items-center justify-center gap-2 transition-colors"
            >
              <Search className="w-4 h-4" /> Áp dụng
            </button>
            <button
              onClick={handleClearFilters}
              className="h-10 px-3 border border-gray-300 text-gray-700 text-sm font-medium rounded-md hover:bg-gray-50 transition-colors"
              title="Xóa bộ lọc"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Content */}
      {isLoading ? (
        <TableSkeleton rows={5} />
      ) : isEmpty ? (
        <div className="bg-white rounded-md border border-gray-200 p-12 flex flex-col items-center text-center">
          <Filter className="w-10 h-10 text-gray-300 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-2">Không tìm thấy bất thường</h3>
          <p className="text-sm text-gray-500 max-w-sm mb-6">Thử giảm ngưỡng xuống 0.5 hoặc bỏ lọc quốc gia để mở rộng kết quả.</p>
          <button onClick={handleClearFilters} className="px-4 py-2 bg-gray-100 text-gray-700 text-sm font-medium rounded-md hover:bg-gray-200 transition-colors">Đặt lại bộ lọc</button>
        </div>
      ) : (
        <>
          <AnomaliesTable data={paginatedData} />
          <Pagination currentPage={page} totalPages={totalPages} onPageChange={setPage} />
        </>
      )}
    </div>
  );
}