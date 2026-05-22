'use client';

import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';

function readCurrentSearch(searchParamsSnapshot: ReturnType<typeof useSearchParams>): string {
  if (typeof window !== 'undefined') {
    return window.location.search;
  }
  const snapshot = searchParamsSnapshot.toString();
  return snapshot ? `?${snapshot}` : '';
}

function serializeValue<T>(state: T, defaultValue: T): string | null {
  if (state === defaultValue) {
    return null;
  }
  if (Array.isArray(state)) {
    return state.length > 0 ? state.join(',') : null;
  }
  if (state === '' || state == null) {
    return null;
  }
  return String(state);
}

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
    if (Array.isArray(defaultValue)) {
      return rawValue
        .split(',')
        .map(value => value.trim())
        .filter(Boolean) as T;
    }
    return rawValue as T;
  };

  const [state, setState] = useState<T>(() => parseFromUrl(currentValue));

  useEffect(() => {
    const urlSearch = readCurrentSearch(searchParams);
    const params = new URLSearchParams(urlSearch);
    const serialized = serializeValue(state, defaultValue);
    if (serialized == null) {
      params.delete(key);
    } else {
      params.set(key, serialized);
    }
    const nextSearch = params.toString();
    const nextUrl = nextSearch ? `${pathname}?${nextSearch}` : pathname;
    const currentUrl = `${pathname}${urlSearch}`;
    if (nextUrl !== currentUrl) {
      router.replace(nextUrl, { scroll: false });
    }
  }, [defaultValue, key, pathname, router, searchParams, state]);

  useEffect(() => {
    if (currentValue === lastUrlValueRef.current) return;
    const next = parseFromUrl(currentValue);
    lastUrlValueRef.current = currentValue;
    const isDifferent = Array.isArray(next)
      ? JSON.stringify(next) !== JSON.stringify(state)
      : next !== state;
    if (isDifferent) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setState(next);
    }
  }, [currentValue, state]);

  return [state, setState];
}
