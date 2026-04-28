'use client';
import { useIndicators } from '@/lib/hooks/useIndicators';

interface Props {
  selected: string;
  onChange: (indicator: string) => void;
}

export default function IndicatorSelector({ selected, onChange }: Props) {
  const { data: indicators, isLoading } = useIndicators();

  if (isLoading) return <div>Loading indicators...</div>;

  const filtered = indicators?.filter((i: any) => 
    ['Growth', 'Fiscal', 'Monetary', 'Social'].includes(i.category)
  );

  return (
    <select
      value={selected}
      onChange={(e) => onChange(e.target.value)}
      className="border rounded p-2 w-64"
    >
      {filtered?.map((ind: any) => (
        <option key={ind.code} value={ind.code}>
          {ind.name} ({ind.unit})
        </option>
      ))}
    </select>
  );
}