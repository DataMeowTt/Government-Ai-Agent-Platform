'use client';
import { useCountries } from '@/lib/hooks/useCountries';

interface Props {
  selected: string[];
  onChange: (codes: string[]) => void;
  max?: number;
}

export default function MultiCountrySelector({ selected, onChange, max = 5 }: Props) {
  const { data: countries, isLoading } = useCountries();

  if (isLoading) return <div>Loading countries...</div>;

  const handleToggle = (code: string) => {
    if (selected.includes(code)) {
      onChange(selected.filter(c => c !== code));
    } else {
      if (selected.length >= max) {
        alert(`You can select up to ${max} countries`);
        return;
      }
      onChange([...selected, code]);
    }
  };

  return (
    <div className="border rounded p-2 max-h-48 overflow-y-auto">
      {countries?.map((country: any) => (
        <label key={country.country_code} className="flex items-center space-x-2 p-1 hover:bg-gray-50">
          <input
            type="checkbox"
            checked={selected.includes(country.country_code)}
            onChange={() => handleToggle(country.country_code)}
            className="rounded"
          />
          <span>{country.country_name} ({country.country_code})</span>
        </label>
      ))}
    </div>
  );
}