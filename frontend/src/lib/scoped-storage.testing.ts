/**
 * localStorage stand-in for the test suite.
 *
 * vitest runs in the `node` environment (see vitest.config.ts), so there is no
 * `window` and every scoped store correctly no-ops. Tests that need to prove
 * what actually lands in storage install this first. Kept out of the `*.test.ts`
 * glob so it is a shared fixture rather than a suite of its own.
 */

class MemoryStorage {
  private readonly entries = new Map<string, string>();

  get length(): number {
    return this.entries.size;
  }

  key(index: number): string | null {
    return [...this.entries.keys()][index] ?? null;
  }

  getItem(key: string): string | null {
    return this.entries.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.entries.set(key, String(value));
  }

  removeItem(key: string): void {
    this.entries.delete(key);
  }

  clear(): void {
    this.entries.clear();
  }

  /** Every key currently held, for assertions about what leaked where. */
  keys(): string[] {
    return [...this.entries.keys()];
  }
}

// `globalThis.window` is declared as a full `Window` by the DOM lib, so the
// stand-in is assigned through an index signature rather than pretending to
// satisfy it.
const mutableGlobal = globalThis as unknown as Record<string, unknown>;

/**
 * Install a fresh in-memory `window.localStorage`. The listener hooks are
 * inert: nothing in these tests renders, so no store ever subscribes.
 */
export function installMemoryStorage(): MemoryStorage {
  const localStorage = new MemoryStorage();
  mutableGlobal.window = {
    localStorage,
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => true,
  };
  return localStorage;
}

export function uninstallMemoryStorage(): void {
  delete mutableGlobal.window;
}
