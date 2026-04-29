'use client';
import { useSearchParams, useRouter, usePathname } from 'next/navigation';
import { useState, useEffect } from 'react';

export function useUrlState<T>(key: string, defaultValue: T): [T, (val: T) => void] {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const [state, setState] = useState<T>(() => {
    const val = searchParams.get(key);
    if (val === null) return defaultValue;
    if (typeof defaultValue === 'number') return Number(val) as T;
    if (Array.isArray(defaultValue)) return val.split(',') as T;
    return val as T;
  });

  useEffect(() => {
    const params = new URLSearchParams(searchParams.toString());
    const strVal = state === defaultValue || !state || (Array.isArray(state) && state.length === 0) 
      ? null 
      : (Array.isArray(state) ? state.join(',') : String(state));

    if (params.get(key) !== strVal) {
      if (strVal) params.set(key, strVal); else params.delete(key);
      router.replace(`${pathname}?${params.toString()}`, { scroll: false });
    }
  }, [state]);

  useEffect(() => {
    const val = searchParams.get(key);
    if (val === null) setState(defaultValue);
    else if (typeof defaultValue === 'number') setState(Number(val) as T);
    else if (Array.isArray(defaultValue)) setState(val.split(',') as T);
    else setState(val as T);
  }, [searchParams.get(key)]);

  return [state, setState];
}