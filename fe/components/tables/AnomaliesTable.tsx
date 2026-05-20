'use client';
import Link from 'next/link';
import { AnomalyItem } from '@/lib/types';
import { useIndicators } from '@/lib/hooks/useIndicators';
import { formatIndicatorValue, formatNumber, formatYear, getAnomalyColor } from '@/lib/utils/format';

interface Props {
  data: AnomalyItem[];
}

export default function AnomaliesTable({ data }: Props) {
  const indicatorsQuery = useIndicators();
  const indicatorMap = new Map((indicatorsQuery.data || []).map((item) => [item.code, item]));
  const rows = data
    .slice()
    .sort((a, b) => a.year - b.year)
    .map((item, index) => ({ item, index }));

  return (
    <div className="overflow-hidden rounded-md border border-slate-200 bg-white shadow-sm">
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr>
              <th className="px-4 py-3 text-left font-semibold">Quốc gia</th>
              <th className="px-4 py-3 text-left font-semibold">Năm</th>
              <th className="px-4 py-3 text-left font-semibold">Chỉ số</th>
              <th className="px-4 py-3 text-right font-semibold">Giá trị thực</th>
              <th className="px-4 py-3 text-right font-semibold">
                <span title="Mức độ lệch của giá trị so với xu hướng lịch sử của chỉ số">Điểm bất thường thống kê</span>
              </th>
              <th className="px-4 py-3 text-right font-semibold">Thao tác</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 bg-white">
            {rows.map(({ item, index }) => {
              const indicator = indicatorMap.get(item.indicator);
              const label = indicator ? `${indicator.name} (${indicator.code})` : item.indicator;
              const unit = indicator?.unit || '';
              const prompt = encodeURIComponent(
                `Phân tích bất thường của chỉ số ${indicator?.name || item.indicator} tại ${item.country_name || item.country_code} năm ${formatYear(item.year)}. Giá trị là ${formatIndicatorValue(item.actual_value, unit)} ${unit ? `(${unit})` : ''}. Điểm bất thường thống kê là ${formatNumber(item.anomaly_score, 3)}. Hãy giải thích ý nghĩa kinh tế và các khả năng cần kiểm tra thêm.`
              );
              return (
                <tr key={`${item.country_code}-${item.indicator}-${item.year}-${index}`} className="hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <Link href={`/countries/${item.country_code}`} className="font-medium text-slate-900 hover:underline">
                      {item.country_name || item.country_code}
                    </Link>
                  </td>
                  <td className="px-4 py-3 font-mono">{formatYear(item.year)}</td>
                  <td className="px-4 py-3">{label}</td>
                  <td className="px-4 py-3 text-right">
                    {formatIndicatorValue(item.actual_value, indicator?.unit)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <span className={`rounded px-2 py-1 text-xs font-medium ${getAnomalyColor(item.anomaly_score)}`}>
                      {formatNumber(item.anomaly_score, 3)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      href={`/chat?q=${prompt}`}
                      className="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100"
                    >
                      Phân tích
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
