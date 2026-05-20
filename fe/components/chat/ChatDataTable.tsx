import { useMemo, useState } from 'react';
import type { AiChatResponse } from '@/lib/types/aiChat';
import { formatCellValue } from '@/lib/utils/format';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function getRows(response?: AiChatResponse) {
  const firstData = response?.data?.[0];

  if (isRecord(firstData) && Array.isArray(firstData.rows)) {
    return firstData.rows.filter(isRecord);
  }

  if (Array.isArray(response?.chart?.data)) {
    return response.chart.data.filter(isRecord);
  }

  return [];
}

function formatCell(column: string, value: unknown) {
  return formatCellValue(column, value);
}

function exportCsv(rows: Record<string, unknown>[], columns: string[]) {
  const header = columns.join(',');
  const lines = rows.map((row) =>
    columns
      .map((column) => {
        const value = formatCell(column, row[column]);
        return `"${String(value).replace(/"/g, '""')}"`;
      })
      .join(',')
  );
  const csv = [header, ...lines].join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `du-lieu-phan-tich-${Date.now()}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export default function ChatDataTable({ response }: { response?: AiChatResponse }) {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const rows = getRows(response);

  if (rows.length === 0) {
    return null;
  }

  const visibleRows = rows.slice(0, 10);
  const columns = useMemo(() => Object.keys(rows[0] || {}), [rows]);

  return (
    <>
      <div className="mt-4 rounded-md border border-slate-200">
        <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2">
          <h4 className="text-sm font-semibold text-slate-900">Bảng dữ liệu</h4>
          <div className="flex items-center gap-2">
            {rows.length > 10 ? <span className="text-xs text-slate-500">Hiển thị 10 / {rows.length} dòng</span> : null}
            {rows.length > 10 ? (
              <button
                type="button"
                onClick={() => setIsModalOpen(true)}
                className="rounded-md border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
              >
                Xem tất cả
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => exportCsv(rows, columns)}
              className="rounded-md border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
            >
              Tải CSV
            </button>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50">
              <tr>
                {columns.map((column) => (
                  <th key={column} className="whitespace-nowrap px-3 py-2 text-left text-xs font-semibold text-slate-600">
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white">
              {visibleRows.map((row, index) => (
                <tr key={`${index}-${columns.map((column) => formatCell(column, row[column])).join('|')}`}>
                  {columns.map((column) => (
                    <td key={column} className="whitespace-nowrap px-3 py-2 text-slate-700">
                      {formatCell(column, row[column])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {isModalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
          <div className="max-h-[85vh] w-full max-w-5xl overflow-hidden rounded-md border border-slate-200 bg-white shadow-lg">
            <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
              <h5 className="text-sm font-semibold text-slate-900">Toàn bộ dữ liệu ({rows.length} dòng)</h5>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => exportCsv(rows, columns)}
                  className="rounded-md border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                >
                  Tải CSV
                </button>
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="rounded-md border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                >
                  Đóng
                </button>
              </div>
            </div>
            <div className="max-h-[72vh] overflow-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="sticky top-0 bg-slate-50">
                  <tr>
                    {columns.map((column) => (
                      <th key={column} className="whitespace-nowrap px-3 py-2 text-left text-xs font-semibold text-slate-600">
                        {column}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {rows.map((row, index) => (
                    <tr key={`${index}-${columns.map((column) => formatCell(column, row[column])).join('|')}`}>
                      {columns.map((column) => (
                        <td key={column} className="whitespace-nowrap px-3 py-2 text-slate-700">
                          {formatCell(column, row[column])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
