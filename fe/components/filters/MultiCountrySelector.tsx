'use client';
import { useCountries } from '@/lib/hooks/useCountries';
import { Country } from '@/lib/types';

interface Props { selected: string[]; onChange: (codes: string[]) => void; max?: number; }

export default function MultiCountrySelector({ selected, onChange, max = 5 }: Props) {
  const { data: countries, isLoading } = useCountries();
  if (isLoading) return <div className="p-2 text-gray-500 animate-pulse">Đang tải...</div>;

  const handleToggle = (code: string) => {
    if (selected.includes(code)) onChange(selected.filter(c => c !== code));
    else if (selected.length < max) onChange([...selected, code]);
    else alert(`Tối đa ${max} quốc gia`);
  };

  return (
    <div className="border rounded p-2 max-h-48 overflow-y-auto bg-white">
      {countries?.map((c: Country) => (
        <label key={c.country_code} className="flex items-center space-x-2 p-1 hover:bg-gray-50 cursor-pointer">
          <input type="checkbox" checked={selected.includes(c.country_code)} onChange={() => handleToggle(c.country_code)} className="rounded" />
          <span className="text-sm">{c.country_name} ({c.country_code})</span>
        </label>
      ))}
    </div>
  );
}