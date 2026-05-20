'use client';
import { useSearchParams, useRouter, usePathname } from 'next/navigation';
import { useState, useEffect, useRef } from 'react';

export function useUrlState<T>(key: string, defaultValue: T): [T, (val: T) => void] {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const currentValue = searchParams.get(key);
  const lastUrlValueRef = useRef<string | null>(currentValue);

  const parseFromUrl = (rawValue: string | null): T => {
    if (rawValue === null) return defaultValue;
    if (typeof defaultValue === 'number') {
      const parsed = Number(rawValue);
      return (Number.isFinite(parsed) ? parsed : defaultValue) as T;
    }
    if (Array.isArray(defaultValue)) return rawValue.split(',') as T;
    return rawValue as T;
  };

  const [state, setState] = useState<T>(() => {
    return parseFromUrl(currentValue);
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
  }, [state, pathname, router, key, defaultValue, searchParams]);

  useEffect(() => {
    if (currentValue === lastUrlValueRef.current) return;
    const next = parseFromUrl(currentValue);
    lastUrlValueRef.current = currentValue;

    const isDifferent = typeof next === 'object'
      ? JSON.stringify(next) !== JSON.stringify(state)
      : next !== state;

    if (isDifferent) {
      setState(next);
    }
  }, [currentValue, state]);

  return [state, setState];
}
