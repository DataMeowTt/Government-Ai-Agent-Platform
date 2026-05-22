interface TabYearlyTableProps {
  data: Array<{ year: number; [key: string]: number | string | null | undefined }>;
  columns: Array<{ accessor: string; header: string }>;
}

export default function TabYearlyTable({ data, columns }: TabYearlyTableProps) {
  if (!data.length) return <div className="p-4 text-center text-sm text-slate-500 border border-dashed border-slate-300 rounded-md">Không có dữ liệu hiển thị.</div>;
  return (
    <div className="bg-white rounded-md border border-slate-200 overflow-hidden">
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr>
              <th className="px-4 py-2.5 text-left font-semibold text-slate-600">Năm</th>
              {columns.map(col => (
                <th key={col.accessor} className="px-4 py-2.5 text-left font-semibold text-slate-600">{col.header}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.map(row => (
              <tr key={row.year} className="hover:bg-slate-50/50 transition-colors">
                <td className="px-4 py-2 font-mono text-slate-700">{row.year}</td>
                {columns.map(col => (
                  <td key={col.accessor} className="px-4 py-2 text-slate-800 font-medium">
                    {row[col.accessor] != null ? Number(row[col.accessor]).toFixed(2) : 'N/A'}
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
