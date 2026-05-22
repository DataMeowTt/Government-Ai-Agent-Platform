'use client';
import { ArrowLeft, Download, GitCompare } from 'lucide-react';
import { useRouter } from 'next/navigation';

interface CountryHeaderProps {
  countryCode: string;
  countryName: string;
  latestYear: number | null;
  onExport: () => void;
  onCompare: () => void;
}

export default function CountryHeader({ countryCode, countryName, latestYear, onExport, onCompare }: CountryHeaderProps) {
  const router = useRouter();
  return (
    <div className="h-16 flex items-center justify-between px-6 border-b border-gray-200 bg-white rounded-t-md">
      <button onClick={() => router.push('/countries')} className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900 transition-colors">
        <ArrowLeft className="w-4 h-4" /> Danh sách
      </button>
      <div className="text-center">
        <h1 className="text-xl font-bold text-gray-900">Hồ sơ Kinh tế: {countryName} ({countryCode})</h1>
        <p className="text-xs text-gray-500">Dữ liệu đến năm {latestYear ?? '...'}</p>
      </div>
      <div className="flex items-center gap-3">
        <button onClick={onCompare} className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-blue-600 border border-blue-200 rounded-md hover:bg-blue-50 transition-colors">
          <GitCompare className="w-4 h-4" /> So sánh nhanh
        </button>
        <button onClick={onExport} className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50 transition-colors">
          <Download className="w-4 h-4" /> Xuất báo cáo
        </button>
      </div>
    </div>
  );
}
