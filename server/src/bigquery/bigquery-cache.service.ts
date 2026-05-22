import { Injectable } from '@nestjs/common';

interface CacheEntry<T> {
  value: T;
  expiresAt: number;
}

@Injectable()
export class BigQueryCacheService {
  private readonly cache = new Map<string, CacheEntry<unknown>>();

  get<T>(key: string): T | undefined {
    const entry = this.cache.get(key);
    if (!entry) {
      return undefined;
    }

    if (Date.now() >= entry.expiresAt) {
      this.cache.delete(key);
      return undefined;
    }

    return entry.value as T;
  }

  set<T>(key: string, value: T, ttlSeconds: number): void {
    const ttl = Math.max(1, ttlSeconds);
    this.cache.set(key, {
      value,
      expiresAt: Date.now() + ttl * 1000,
    });
  }
}

