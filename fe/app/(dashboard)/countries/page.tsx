'use client';
import { useCountries } from '@/lib/hooks/useCountries';
import { useDataState } from '@/lib/hooks/useDataState';
import { TableSkeleton } from '@/components/ui/Skeletons';
import { Search, Globe2, Filter } from 'lucide-react';
import { useState, useMemo } from 'react';
import Link from 'next/link';

export default function CountriesPage() {
  const { data: countries, isLoading, isEmpty, isError, error } = useDataState(useCountries());
  const [search, setSearch] = useState('');

  const filteredCountries = useMemo(() => {
    if (!countries) return [];
    const q = search.toLowerCase();
    return countries.filter(c =>
      c.country_name.toLowerCase().includes(q) || c.country_code.toLowerCase().includes(q)
    );
  }, [countries, search]);

  if (isError) return <div className="p-4 bg-red-50 text-red-700 rounded border border-red-200">Lỗi: {error?.message}</div>;

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <h1 className="text-2xl font-bold text-gray-900">Danh sách Quốc gia</h1>
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <span className="font-medium text-gray-900">{filteredCountries.length}</span> quốc gia
        </div>
      </div>

      {/* Control Bar */}
      <div className="bg-white p-4 rounded-md border border-gray-200 shadow-sm flex flex-col sm:flex-row gap-4 items-center justify-between">
        <div className="relative w-full sm:w-72">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Tìm theo tên hoặc mã..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 h-10 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <Filter className="w-4 h-4" />
          <span>Sắp xếp: Mặc định</span>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-md border border-gray-200 overflow-hidden">
        {isLoading ? (
          <TableSkeleton rows={8} />
        ) : isEmpty ? (
          <div className="p-12 flex flex-col items-center text-center">
            <Globe2 className="w-10 h-10 text-gray-300 mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">Không có dữ liệu</h3>
            <p className="text-sm text-gray-500">API chưa trả về danh sách quốc gia nào.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Mã</th>
                  <th className="px-6 py-3.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Quốc gia</th>
                  <th className="px-6 py-3.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Nhóm thu nhập</th>
                  <th className="px-6 py-3.5 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">Thao tác</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {filteredCountries.length > 0 ? filteredCountries.map((country) => (
                  <tr key={country.country_code} className="hover:bg-gray-50/80 transition-colors">
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-mono text-gray-600">{country.country_code}</td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{country.country_name}</td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{country.region || 'Chưa phân loại'}</td>
                    <td className="px-6 py-4 whitespace-nowrap text-right">
                      <Link href={`/countries/${country.country_code}`} className="text-sm font-medium text-blue-600 hover:text-blue-800 transition-colors">
                        Xem chi tiết
                      </Link>
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={4} className="px-6 py-12 text-center text-gray-500">
                      Không tìm thấy quốc gia phù hợp với từ khóa "{search}".
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}