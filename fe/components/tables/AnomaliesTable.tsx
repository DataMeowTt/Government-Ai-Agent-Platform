'use client';
import { formatNumber, getAnomalyColor } from '@/lib/utils/format';
import { AnomalyItem } from '@/lib/types';
import { ArrowUpRight } from 'lucide-react';
import Link from 'next/link';
import { getIndicatorViName } from '@/lib/utils/indicatorTranslations';
interface Props {
  data: AnomalyItem[];
}

export default function AnomaliesTable({ data }: Props) {
  if (!data?.length) return null;

  return (
    <div className="bg-white rounded-md border border-gray-200 overflow-hidden">
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="w-1" />
              <th className="px-6 py-3.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Quốc gia</th>
              <th className="px-6 py-3.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Năm</th>
              <th className="px-6 py-3.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Chỉ số</th>
              <th className="px-6 py-3.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Giá trị thực</th>
              <th className="px-6 py-3.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Điểm</th>
              <th className="px-6 py-3.5 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">Thao tác</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {data.map((item, idx) => {
              const score = item.anomaly_score || 0;
              const severityClass = score >= 0.9 ? 'border-l-4 border-rose-500' : score >= 0.75 ? 'border-l-4 border-amber-500' : 'border-l-4 border-gray-300';
              
              return (
                <tr key={`${item.country_code}-${item.year}-${item.indicator}-${idx}`} className={`hover:bg-gray-50/80 transition-colors ${severityClass}`}>
                  <td className="w-1" />
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                    <Link href={`/countries/${item.country_code}`} className="hover:text-blue-600 hover:underline">
                      {item.country_name || item.country_code}
                    </Link>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{item.year}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600 font-mono">{getIndicatorViName(item.indicator)}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 font-medium">{formatNumber(item.actual_value)}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                    <span className={`px-2 py-1 rounded text-xs font-medium ${getAnomalyColor(item.anomaly_score)}`}>
                      {formatNumber(item.anomaly_score, 3)}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <Link href={`/countries/${item.country_code}`} className="text-gray-400 hover:text-blue-600 transition-colors">
                      <ArrowUpRight className="w-4 h-4" />
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}