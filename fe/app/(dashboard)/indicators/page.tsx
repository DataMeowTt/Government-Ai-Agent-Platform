'use client';
import { useMemo, useState } from 'react';
import Link from 'next/link';
import PageHeader from '@/components/ui/PageHeader';
import FilterBar from '@/components/ui/FilterBar';
import SearchInput from '@/components/ui/SearchInput';
import TableShell from '@/components/ui/TableShell';
import StateBlock from '@/components/ui/StateBlock';
import { TableSkeleton } from '@/components/ui/Skeletons';
import { useIndicators } from '@/lib/hooks/useIndicators';
import { getIndicatorCategoryLabel } from '@/lib/indicatorCategories';
import { DEFAULT_COMPARE_COUNTRIES } from '@/lib/utils/compare';

export default function IndicatorsPage() {
  const { data, isLoading, isError, error } = useIndicators();
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');

  const indicators = data || [];
  const categories = useMemo(
    () => Array.from(new Set(indicators.map((item) => item.category))).sort((a, b) => a.localeCompare(b)),
    [indicators]
  );

  const filtered = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return indicators.filter((item) => {
      const byCategory = !category || item.category === category;
      const bySearch =
        !keyword ||
        item.code.toLowerCase().includes(keyword) ||
        item.name.toLowerCase().includes(keyword) ||
        (item.name_vi || '').toLowerCase().includes(keyword);
      return byCategory && bySearch;
    });
  }, [indicators, category, search]);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Danh mục chỉ số"
        description="Danh mục chỉ số kinh tế kèm đơn vị, nhóm chỉ số và khả năng phân tích."
        actions={<p className="text-sm text-slate-600">Tổng chỉ số: {indicators.length}</p>}
      />

      <FilterBar>
        <div className="md:col-span-8">
          <label className="mb-1 block text-sm font-medium text-slate-700">Tìm kiếm theo tên hoặc mã</label>
          <SearchInput value={search} onChange={setSearch} placeholder="Ví dụ: govdebt_GDP" debounceTime={150} />
        </div>
        <div className="md:col-span-4">
          <label className="mb-1 block text-sm font-medium text-slate-700">Nhóm chỉ số</label>
          <select
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            className="h-10 w-full rounded-md border border-slate-300 px-3 text-sm"
          >
            <option value="">Tất cả nhóm</option>
            {categories.map((item) => (
              <option key={item} value={item}>
                {getIndicatorCategoryLabel(item)}
              </option>
            ))}
          </select>
        </div>
      </FilterBar>

      {isLoading ? <TableSkeleton rows={8} /> : null}

      {isError ? (
        <StateBlock
          mode="error"
          title="Không tải được danh mục chỉ số"
          description={error instanceof Error ? error.message : 'Lỗi không xác định khi tải danh mục chỉ số.'}
        />
      ) : null}

      {!isLoading && !isError && filtered.length === 0 ? (
        <StateBlock
          mode="empty"
          title="Không có chỉ số phù hợp"
          description="Hãy điều chỉnh từ khóa tìm kiếm hoặc nhóm chỉ số."
          action={{
            label: 'Xóa bộ lọc',
            onClick: () => {
              setSearch('');
              setCategory('');
            },
          }}
        />
      ) : null}

      {!isLoading && !isError && filtered.length > 0 ? (
        <TableShell>
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className="px-2 py-3 text-left font-semibold">Tên chỉ số</th>
                <th className="px-2 py-3 text-left font-semibold">Đơn vị</th>
                <th className="px-2 py-3 text-left font-semibold">Nhóm</th>
                <th className="px-2 py-3 text-left font-semibold">Khả năng phân tích</th>
                <th className="px-2 py-3 text-right font-semibold">Thao tác</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white">
              {filtered.map((item) => (
                <tr key={item.code} className="hover:bg-slate-50">
                  <td className="px-2 py-3">
                    <p className="font-medium text-slate-900">
                      {item.name}{' '}
                      {item.supports_trend ? (
                        <span className="ml-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-700">
                          Có xu hướng
                        </span>
                      ) : null}
                      {item.supports_anomaly ? (
                        <span
                          className="ml-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-700"
                          title="Có dữ liệu điểm bất thường thống kê cho chỉ số này"
                          aria-label="Có dữ liệu điểm bất thường thống kê cho chỉ số này"
                        >
                          Hỗ trợ anomaly
                        </span>
                      ) : null}
                    </p>
                    <p className="text-xs text-slate-500">{item.code}</p>
                    {item.description_vi ? <p className="mt-1 text-xs text-slate-600">{item.description_vi}</p> : null}
                  </td>
                  <td className="px-2 py-3">{item.unit || 'Chưa công bố'}</td>
                  <td className="px-2 py-3">{getIndicatorCategoryLabel(item.category)}</td>
                  <td className="px-2 py-3 text-xs text-slate-700">
                    {[
                      item.supports_compare ? 'So sánh' : null,
                      item.supports_trend ? 'Xu hướng' : null,
                      item.supports_anomaly ? 'Bất thường' : null,
                      item.supports_ranking ? 'Xếp hạng' : null,
                    ]
                      .filter(Boolean)
                      .join(', ') || 'Đang cập nhật'}
                  </td>
                  <td className="px-2 py-3">
                    <div className="flex justify-end gap-2">
                      <Link
                        href={`/compare?countries=${DEFAULT_COMPARE_COUNTRIES.join(',')}&indicator=${item.code}&from=2010&to=2023`}
                        className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                      >
                        So sánh
                      </Link>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableShell>
      ) : null}
    </div>
  );
}
