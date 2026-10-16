'use client';

import { useSyncExternalStore } from 'react';

export interface SearchOptions {
  hybridSearch: boolean;
  graphExpansion: boolean;
  rrfSearch: boolean;
  caching: boolean;
  queryExpansion?: {
    enabled: boolean;
    temperature: number;
  };
}

const DEFAULT_OPTIONS: SearchOptions = {
  hybridSearch: false,
  graphExpansion: true,
  rrfSearch: false,
  caching: false,
};

class SearchOptionsStore {
  private listeners = new Map<string, Set<() => void>>();
  private options = new Map<string, SearchOptions>();
  private initializedKeys = new Set<string>();

  private getStorageKey(sessionId?: string) {
    return sessionId
      ? `session-${sessionId}-search-options`
      : 'falkor-evidence-search-options';
  }

  private loadFromStorage(sessionId?: string) {
    const storageKey = this.getStorageKey(sessionId);

    try {
      const stored = localStorage.getItem(storageKey);
      if (stored) {
        this.options.set(storageKey, { ...DEFAULT_OPTIONS, ...JSON.parse(stored) });
      } else {
        this.options.set(storageKey, DEFAULT_OPTIONS);
      }
      this.initializedKeys.add(storageKey);
    } catch (e) {
      console.error('Failed to parse search options from localStorage', e);
      this.options.set(storageKey, DEFAULT_OPTIONS);
      this.initializedKeys.add(storageKey);
    }
  }

  getOptions(sessionId?: string): SearchOptions {
    const storageKey = this.getStorageKey(sessionId);

    if (!this.initializedKeys.has(storageKey) && typeof window !== 'undefined') {
      this.loadFromStorage(sessionId);
    }

    return this.options.get(storageKey) ?? DEFAULT_OPTIONS;
  }

  setOptions(sessionId: string | undefined, newOptions: Partial<SearchOptions>) {
    const storageKey = this.getStorageKey(sessionId);
    const currentOptions = this.getOptions(sessionId);
    const nextOptions = { ...currentOptions, ...newOptions };

    this.options.set(storageKey, nextOptions);
    this.initializedKeys.add(storageKey);

    if (typeof window !== 'undefined') {
      localStorage.setItem(storageKey, JSON.stringify(nextOptions));
    }

    this.notifyListeners(storageKey);
  }

  subscribe(sessionId: string | undefined, listener: () => void) {
    const storageKey = this.getStorageKey(sessionId);
    const keyListeners = this.listeners.get(storageKey) ?? new Set<() => void>();

    keyListeners.add(listener);
    this.listeners.set(storageKey, keyListeners);

    return () => {
      const currentListeners = this.listeners.get(storageKey);
      if (!currentListeners) {
        return;
      }

      currentListeners.delete(listener);

      if (currentListeners.size === 0) {
        this.listeners.delete(storageKey);
      }
    };
  }

  private notifyListeners(storageKey: string) {
    const keyListeners = this.listeners.get(storageKey);
    if (!keyListeners) {
      return;
    }

    keyListeners.forEach(listener => listener());
  }
}

const store = new SearchOptionsStore();

export function useSearchOptions(sessionId?: string) {
  const options = useSyncExternalStore(
    (listener) => store.subscribe(sessionId, listener),
    () => store.getOptions(sessionId),
    () => DEFAULT_OPTIONS
  );

  const updateOptions = (newOptions: Partial<SearchOptions>) => {
    store.setOptions(sessionId, newOptions);
  };

  const toggleHybridSearch = () => {
    store.setOptions(sessionId, { hybridSearch: !store.getOptions(sessionId).hybridSearch });
  };

  const disableHybridSearch = () => {
    store.setOptions(sessionId, { hybridSearch: false });
  };

  const toggleRrfSearch = () => {
    store.setOptions(sessionId, { rrfSearch: !store.getOptions(sessionId).rrfSearch });
  };

  const disableRrfSearch = () => {
    store.setOptions(sessionId, { rrfSearch: false });
  };

  const toggleKeywordCaching = () => {
    store.setOptions(sessionId, { caching: !store.getOptions(sessionId).caching });
  };

  const disableCaching = () => {
    store.setOptions(sessionId, { caching: false });
  };

  return {
    options,
    updateOptions,
    toggleHybridSearch,
    disableHybridSearch,
    toggleRrfSearch,
    disableRrfSearch,
    toggleKeywordCaching,
    disableCaching,
    isLoaded: true,
  };
}

