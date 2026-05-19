import type { AiChatResponse } from '@/lib/types/aiChat';

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
  if (value == null) {
    return '-';
  }

  if (typeof value === 'number') {
    const normalizedColumn = column.toLowerCase();
    if (normalizedColumn === 'year' || normalizedColumn.endsWith('_year')) {
      return String(value);
    }
    return Number.isFinite(value) ? value.toLocaleString('vi-VN', { maximumFractionDigits: 2 }) : '-';
  }

  if (typeof value === 'string' || typeof value === 'boolean') {
    return String(value);
  }

  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export default function ChatDataTable({ response }: { response?: AiChatResponse }) {
  const rows = getRows(response);

  if (rows.length === 0) {
    return null;
  }

  const visibleRows = rows.slice(0, 10);
  const columns = Object.keys(visibleRows[0] || {});

  return (
    <div className="mt-4 rounded-md border border-slate-200">
      <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2">
        <h4 className="text-sm font-semibold text-slate-900">Bảng dữ liệu</h4>
        {rows.length > 10 ? <span className="text-xs text-slate-500">Hiển thị 10 / {rows.length} dòng</span> : null}
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
  );
}
