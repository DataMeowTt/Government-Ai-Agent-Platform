'use client';
import { useIndicators } from '@/lib/hooks/useIndicators';
import { Indicator } from '@/lib/types';

interface Props { selected: string; onChange: (indicator: string) => void; }

export default function IndicatorSelector({ selected, onChange }: Props) {
  const { data: indicators, isLoading } = useIndicators();
  if (isLoading) return <div className="p-2 text-gray-500 animate-pulse">Đang tải...</div>;

  const unique = indicators?.filter((i: Indicator) =>
    ['Growth', 'Fiscal', 'Monetary', 'Social'].includes(i.category)
  ).reduce<Indicator[]>((acc, curr) => {
    if (!acc.some(i => i.code === curr.code)) acc.push(curr);
    return acc;
  }, []);

  return (
    <select value={selected} onChange={(e) => onChange(e.target.value)} className="border rounded p-2 w-64 bg-white shadow-sm">
      {unique?.map((ind) => (
        <option key={ind.code} value={ind.code}>{ind.name} ({ind.unit})</option>
      ))}
    </select>
  );
}