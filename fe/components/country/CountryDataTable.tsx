'use client';
import { useMemo, useState } from 'react';
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
  createColumnHelper,
  SortingState,
} from '@tanstack/react-table';
import { CountryAnalyticsRow } from '@/lib/types';
import { Eye, EyeOff, ArrowUpDown, Table2 } from 'lucide-react';

const INDICATORS = [
  { key: 'actual_growth', label: 'Tăng trưởng (%)' },
  { key: 'trend_growth', label: 'Xu hướng (%)' },
  { key: 'actual_debt', label: 'Nợ công (%)' },
  { key: 'actual_inflation', label: 'Lạm phát CPI (%)' },
  { key: 'actual_poverty', label: 'Nghèo đói (%)' },
  { key: 'actual_unemployment', label: 'Thất nghiệp (%)' },
  { key: 'actual_manuf_share', label: 'Sản xuất (%)' },
  { key: 'actual_agri_share', label: 'Nông nghiệp (%)' },
  { key: 'actual_reer_deviation', label: 'REER Dev (%)' },
];

export default function CountryDataTable({ data }: { data: CountryAnalyticsRow[] }) {
  const columnHelper = createColumnHelper<CountryAnalyticsRow>();
  const [sorting, setSorting] = useState<SortingState>([{ id: 'year', desc: true }]);
  const [visibleCols, setVisibleCols] = useState<Record<string, boolean>>({
    actual_growth: true,
    actual_debt: true,
    actual_inflation: true,
    actual_unemployment: true,
    actual_reer_deviation: true,
  });

  const baseColumns = [
    columnHelper.accessor('year', {
      header: 'Năm',
      cell: info => <span className="font-mono text-slate-700 font-medium">{info.getValue()}</span>,
      enableSorting: true,
    }),
  ];

  const indicatorCols = INDICATORS.map(ind =>
    columnHelper.accessor(ind.key as keyof CountryAnalyticsRow, {
      header: ind.label,
      cell: info => {
        const val = info.getValue();
        if (val == null) return <span className="text-slate-400">N/A</span>;
        return <span className="font-medium text-slate-800">{Number(val).toFixed(2)}%</span>;
      },
      enableSorting: true,
    })
  );

  const columns = useMemo(() => {
    return [...baseColumns, ...indicatorCols.filter(c => c.id != null && visibleCols[c.id as string])];
  }, [visibleCols, indicatorCols, baseColumns]);

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  if (!data || data.length === 0) {
    return (
      <div className="bg-white rounded-md border border-slate-200 p-12 flex flex-col items-center text-center min-h-[300px] justify-center">
        <Table2 className="w-10 h-10 text-slate-300 mb-3" />
        <p className="text-slate-500 font-medium">Chưa có dữ liệu lịch sử để hiển thị.</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-md border border-slate-200 min-h-[300px] flex flex-col overflow-hidden">
      <div className="p-4 border-b border-slate-200 flex items-center justify-between flex-wrap gap-3 bg-slate-50/50">
        <h3 className="text-base font-semibold text-slate-900">Bảng dữ liệu chi tiết theo năm</h3>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500 font-medium">Cột hiển thị:</span>
          <div className="flex gap-1 flex-wrap">
            {INDICATORS.map(ind => (
              <button
                key={ind.key}
                onClick={() => setVisibleCols(prev => ({ ...prev, [ind.key]: !prev[ind.key] }))}
                className="flex items-center gap-1.5 px-2 py-1 text-xs rounded-md border border-slate-200 bg-white transition-colors hover:bg-slate-50 hover:border-slate-300"
                title={visibleCols[ind.key] ? 'Ẩn cột' : 'Hiện cột'}
              >
                {visibleCols[ind.key] ? <Eye className="w-3 h-3 text-blue-600" /> : <EyeOff className="w-3 h-3 text-slate-400" />}
                {ind.label.split(' ')[0]}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div className="overflow-x-auto flex-1">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 sticky top-0 z-10 shadow-sm">
            {table.getHeaderGroups().map(hg => (
              <tr key={hg.id}>
                {hg.headers.map(header => (
                  <th
                    key={header.id}
                    onClick={header.column.getToggleSortingHandler()}
                    className="px-4 py-3 text-left font-semibold text-slate-600 cursor-pointer select-none hover:bg-slate-100 whitespace-nowrap transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {header.column.getIsSorted() && <ArrowUpDown className="w-3 h-3 text-blue-500" />}
                    </div>
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody className="divide-y divide-slate-100">
            {table.getRowModel().rows.map(row => (
              <tr key={row.id} className="hover:bg-slate-50/50 transition-colors">
                {row.getVisibleCells().map(cell => (
                  <td key={cell.id} className="px-4 py-3 whitespace-nowrap">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}