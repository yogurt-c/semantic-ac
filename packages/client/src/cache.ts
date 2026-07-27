const DEFAULT_MAX_ENTRIES = 500;

export class PrefixCache<T> {
  private readonly store = new Map<string, T>();

  constructor(private readonly maxEntries: number = DEFAULT_MAX_ENTRIES) {}

  get(prefix: string): T | undefined {
    return this.store.get(prefix);
  }

  has(prefix: string): boolean {
    return this.store.has(prefix);
  }

  set(prefix: string, value: T): void {
    if (this.maxEntries <= 0) {
      return;
    }
    if (!this.store.has(prefix) && this.store.size >= this.maxEntries) {
      const oldestKey = this.store.keys().next().value;
      if (oldestKey !== undefined) {
        this.store.delete(oldestKey);
      }
    }
    this.store.set(prefix, value);
  }

  clear(): void {
    this.store.clear();
  }
}
