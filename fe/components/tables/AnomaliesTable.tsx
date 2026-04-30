'use client';
import { useMemo } from 'react';
import { formatNumber, getAnomalyColor } from '@/lib/utils/format';
import { getIndicatorViName } from '@/lib/utils/indicatorTranslations';
import { useIndicators } from '@/lib/hooks/useIndicators';
import { AnomalyItem } from '@/lib/types';
import Link from 'next/link';

interface Props {
  data: AnomalyItem[];
}

export default function AnomaliesTable({ data }: Props) {
  const { data: indicators } = useIndicators();

  const indicatorUnitMap = useMemo(() => {
    if (!indicators) return {};
    const map: Record<string, string> = {};
    indicators.forEach(ind => { map[ind.code] = ind.unit; });
    return map;
  }, [indicators]);

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
              const rowKey = `${item.country_code}-${item.year}-${item.indicator}-${idx}`;
              const score = item.anomaly_score || 0;
              const severityClass = score >= 0.9 ? 'border-l-4 border-rose-500' : score >= 0.75 ? 'border-l-4 border-amber-500' : 'border-l-4 border-gray-300';

              const unit = indicatorUnitMap[item.indicator];
              const indicatorLabel = unit
                ? `${getIndicatorViName(item.indicator)} (${unit})`
                : getIndicatorViName(item.indicator);

              return (
                <tr key={rowKey} className={`hover:bg-gray-50/80 transition-colors ${severityClass}`}>
                  <td className="w-1" />
                  <td className="px-6 py-2 whitespace-nowrap text-sm font-medium text-gray-900">
                    <Link href={`/countries/${item.country_code}`} className="hover:text-blue-600 hover:underline">
                      {item.country_name || item.country_code}
                    </Link>
                  </td>
                  <td className="px-6 py-2 whitespace-nowrap text-sm text-gray-500">{item.year}</td>
                  <td className="px-6 py-2 whitespace-nowrap text-sm text-gray-600 font-mono">{indicatorLabel}</td>
                  <td className="px-6 py-2 whitespace-nowrap text-sm text-gray-900 font-medium">{formatNumber(item.actual_value)}</td>
                  <td className="px-6 py-2 whitespace-nowrap text-sm">
                    <span className={`px-2 py-1 rounded text-xs font-medium ${getAnomalyColor(item.anomaly_score)}`}>
                      {formatNumber(item.anomaly_score, 3)}
                    </span>
                  </td>
                  <td className="px-6 py-2 whitespace-nowrap text-right text-sm font-medium">
                    <Link
                      href={`/countries/${item.country_code}`}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-50 text-blue-700 text-xs font-semibold rounded-md hover:bg-blue-100 hover:text-blue-800 transition-colors"
                    >
                      Xem chi tiết
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