'use client';
import { useMemo, useState } from 'react';
import Link from 'next/link';
import { Plus } from 'lucide-react';
import PageHeader from '@/components/ui/PageHeader';
import FilterBar from '@/components/ui/FilterBar';
import SearchInput from '@/components/ui/SearchInput';
import TableShell from '@/components/ui/TableShell';
import StateBlock from '@/components/ui/StateBlock';
import { TableSkeleton } from '@/components/ui/Skeletons';
import { useCountries } from '@/lib/hooks/useCountries';
import type { Country } from '@/lib/types';
import { buildCompareCountries } from '@/lib/utils/compare';

export default function CountriesPage() {
  const { data, isLoading, isError, error } = useCountries();
  const [search, setSearch] = useState('');

  const countries = useMemo(() => {
    const map = new Map<string, Country>();
    (data || []).forEach((item) => {
      if (!map.has(item.country_code)) map.set(item.country_code, item);
    });
    return Array.from(map.values());
  }, [data]);

  const filtered = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    if (!keyword) return countries;
    return countries.filter(
      (item) =>
        item.country_name.toLowerCase().includes(keyword) || item.country_code.toLowerCase().includes(keyword)
    );
  }, [countries, search]);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Quốc gia"
        description="Danh sách quốc gia có dữ liệu trong hệ thống."
        actions={<p className="text-sm text-slate-600">Tổng số quốc gia: {countries.length}</p>}
      />

      <FilterBar>
        <div className="md:col-span-6">
          <label className="mb-1 block text-sm font-medium text-slate-700">Tìm kiếm quốc gia</label>
          <SearchInput
            placeholder="Nhập tên quốc gia hoặc mã quốc gia"
            value={search}
            onChange={setSearch}
            debounceTime={200}
          />
        </div>
      </FilterBar>

      {isLoading ? <TableSkeleton rows={8} /> : null}

      {isError ? (
        <StateBlock
          mode="error"
          title="Không tải được danh sách quốc gia"
          description={error instanceof Error ? error.message : 'Đã có lỗi khi tải danh sách quốc gia.'}
        />
      ) : null}

      {!isLoading && !isError && filtered.length === 0 ? (
        <StateBlock
          mode="empty"
          title="Không có quốc gia phù hợp"
          description="Không tìm thấy quốc gia theo từ khóa hiện tại."
          action={{
            label: 'Xóa bộ lọc',
            onClick: () => setSearch(''),
          }}
        />
      ) : null}

      {!isLoading && !isError && filtered.length > 0 ? (
        <TableShell>
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className="px-4 py-3 text-left font-semibold">Mã quốc gia</th>
                <th className="px-4 py-3 text-left font-semibold">Tên quốc gia</th>
                <th className="px-4 py-3 text-left font-semibold">Khu vực</th>
                <th className="px-4 py-3 text-right font-semibold">Thao tác</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white">
              {filtered.map((country) => (
                <tr key={country.country_code} className="hover:bg-slate-50">
                  <td className="px-4 py-3 font-mono">{country.country_code}</td>
                  <td className="px-4 py-3 font-medium text-slate-900">{country.country_name}</td>
                  <td className="px-4 py-3">{country.region || 'N/A'}</td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-2">
                      <Link
                        href={`/countries/${country.country_code}`}
                        className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                      >
                        Xem hồ sơ
                      </Link>
                      <Link
                        href={`/compare?countries=${buildCompareCountries(country.country_code).join(',')}&indicator=govdebt_GDP&from=2010&to=2023`}
                        className="inline-flex items-center gap-1 rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                      >
                        <Plus className="h-3 w-3" />
                        Thêm vào so sánh
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
