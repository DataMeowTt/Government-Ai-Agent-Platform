'use client';

import { Search, X } from 'lucide-react';
import { cn } from '@/lib/utils/cn';

interface SearchInputProps {
  placeholder?: string;
  value: string;
  onChange: (value: string) => void;
  debounceTime?: number;
  className?: string;
  id?: string;
  name?: string;
  label?: string;
  hideLabel?: boolean;
}

export default function SearchInput({
  placeholder = 'Tìm kiếm...',
  value,
  onChange,
  className,
  id,
  name,
  label,
  hideLabel = true,
}: SearchInputProps) {
  const inputId = id || `search-input-${name || 'value'}`;

  return (
    <div className={cn('relative w-full min-w-[240px]', className)}>
      {label ? (
        <label
          htmlFor={inputId}
          className={hideLabel ? 'sr-only' : 'mb-1 block text-sm font-medium text-slate-700'}
        >
          {label}
        </label>
      ) : null}
      <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
      <input
        id={inputId}
        name={name || inputId}
        type="text"
        placeholder={placeholder}
        value={value}
        onChange={event => onChange(event.target.value)}
        className="h-10 w-full rounded-md border border-gray-300 pl-10 pr-10 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
      {value ? (
        <button
          type="button"
          onClick={() => onChange('')}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
        >
          <X className="h-4 w-4" />
        </button>
      ) : null}
    </div>
  );
}
