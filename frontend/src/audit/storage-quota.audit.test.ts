/**
 * AUDIT (shard: storage-quota, finding WS-4). Each test here asserts the
 * behaviour a careful operator would expect; a FAILING test is the proof of a
 * finding, not a broken suite. Pure-module tests only: the real reader stores
 * are executed against in-memory stand-ins, nothing renders.
 *
 * WS-4: one scroll position and one page-ratio map per chapter, per profile,
 * forever. Nothing prunes them, so a year of reading fills the origin's
 * localStorage quota; from then on every write on the origin throws, the
 * scoped writer swallows it, and the reader silently stops remembering ANY
 * position — including the chapter being read right now.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  readScopedString,
  setStorageScope,
  writeScopedString,
} from "@/lib/scoped-storage";
import {
  installMemoryStorage,
  uninstallMemoryStorage,
} from "@/lib/scoped-storage.testing";
import { readPageRatios, writePageRatios } from "@/features/reader/page-ratios";
import { readReaderPosition, writeReaderPosition } from "@/features/reader/scroll-storage";

const ALICE = { userId: 1, profileId: 10 };
const BOB = { userId: 1, profileId: 11 };

const SCROLL_PREFIX = "manhwamaniacs-reader-scroll:";
const RATIO_PREFIX = "manhwamaniacs-reader-page-ratios:";

/** A realistic 40-page webtoon chapter: tall pages, two-decimal ratios. */
const SHAPES = Array.from({ length: 40 }, (_, i) => 1.4 + (i % 7) * 2.13);

function chapter(i: number): string {
  return `mangadex:some-series-slug-${i % 40}:chapter-${i}`;
}

function openChapter(i: number): void {
  writeReaderPosition(chapter(i), { page: 12, offset: 340 });
  writePageRatios(chapter(i), SHAPES);
}

/**
 * localStorage that enforces a byte budget the way a browser does: the write
 * that would cross it throws `QuotaExceededError` and stores nothing.
 */
class QuotaStorage {
  private readonly entries = new Map<string, string>();
  constructor(private readonly capacity: number) {}
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
    const previous = this.entries.get(key);
    const used = this.chars() - (previous === undefined ? 0 : key.length + previous.length);
    if (used + key.length + value.length > this.capacity) {
      throw new DOMException("The quota has been exceeded.", "QuotaExceededError");
    }
    this.entries.set(key, String(value));
  }
  removeItem(key: string): void {
    this.entries.delete(key);
  }
  clear(): void {
    this.entries.clear();
  }
  chars(): number {
    let total = 0;
    for (const [key, value] of this.entries) total += key.length + value.length;
    return total;
  }
  keys(): string[] {
    return [...this.entries.keys()];
  }
  /** Fill whatever slack is left, so the next write of any size must evict. */
  fill(): void {
    const slack = this.capacity - this.chars() - "pad".length;
    if (slack > 0) this.entries.set("pad", "x".repeat(slack));
  }
}

const mutableGlobal = globalThis as unknown as Record<string, unknown>;

function installQuotaStorage(capacity: number): QuotaStorage {
  const localStorage = new QuotaStorage(capacity);
  mutableGlobal.window = {
    localStorage,
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => true,
  };
  return localStorage;
}

function countKeys(keys: string[], prefix: string): number {
  return keys.filter((key) => key.startsWith(prefix)).length;
}

/**
 * The bound, found by writing until a known entry falls off, so the tests
 * assert a bound exists rather than restating the constant that sets it.
 *
 * Presence is checked on the raw key, never through a read: a read is a use,
 * and probing with one would keep the probe young forever.
 */
function boundOnPositions(
  storage: { getItem(key: string): string | null },
  probe: string,
): number {
  const probeKey = `${SCROLL_PREFIX}${probe}::u1:p10`;
  let bound = 0;
  writeReaderPosition(probe, { page: 1, offset: 0 });
  while (storage.getItem(probeKey) !== null) {
    bound += 1;
    writeReaderPosition(`${probe}-filler-${bound}`, { page: 1, offset: 0 });
    if (bound > 5000) throw new Error("no bound on scroll positions");
  }
  return bound;
}

afterEach(() => {
  setStorageScope(null);
  uninstallMemoryStorage();
});

describe("WS-4 per-chapter reader keys are bounded per profile", () => {
  let storage = installMemoryStorage();

  beforeEach(() => {
    storage = installMemoryStorage();
    setStorageScope(ALICE);
  });

  it("holds a fixed number of positions and ratio maps however many chapters are opened", () => {
    for (let i = 0; i < 1500; i += 1) openChapter(i);
    const scrollAt1500 = countKeys(storage.keys(), SCROLL_PREFIX);
    const ratiosAt1500 = countKeys(storage.keys(), RATIO_PREFIX);

    for (let i = 1500; i < 2000; i += 1) openChapter(i);

    expect(scrollAt1500).toBeLessThanOrEqual(1000);
    expect(ratiosAt1500).toBeLessThanOrEqual(1000);
    // The count has stopped moving: it is a bound, not a slower leak.
    expect(countKeys(storage.keys(), SCROLL_PREFIX)).toBe(scrollAt1500);
    expect(countKeys(storage.keys(), RATIO_PREFIX)).toBe(ratiosAt1500);
  });

  it("evicts the chapter written longest ago, and a re-written chapter is young again", () => {
    const limit = boundOnPositions(storage, "first");

    writeReaderPosition("keep", { page: 7, offset: 70 });
    for (let i = 0; i < limit - 1; i += 1) {
      writeReaderPosition(`wave-a-${i}`, { page: 1, offset: 0 });
    }
    // Touch "keep" just before it would fall off the end...
    writeReaderPosition("keep", { page: 7, offset: 70 });
    for (let i = 0; i < limit - 1; i += 1) {
      writeReaderPosition(`wave-b-${i}`, { page: 1, offset: 0 });
    }

    // ...and it outlives every chapter written around it the first time.
    expect(readReaderPosition("keep")).toEqual({ page: 7, offset: 70 });
    expect(readReaderPosition("wave-a-0")).toBeNull();
    expect(readReaderPosition(`wave-b-${limit - 2}`)).toEqual({ page: 1, offset: 0 });
  });

  it("keeps positions written before the bound existed readable, and counts them against it", () => {
    // What the unbounded store left behind: bare entries, no bookkeeping.
    for (let i = 0; i < 50; i += 1) {
      storage.setItem(`${SCROLL_PREFIX}legacy-${i}::u1:p10`, "4200");
    }

    writeReaderPosition("fresh", { page: 2, offset: 20 });
    expect(readReaderPosition("legacy-7")).toEqual({ page: 1, offset: 4200 });
    expect(readReaderPosition("fresh")).toEqual({ page: 2, offset: 20 });

    for (let i = 0; i < 2000; i += 1) {
      writeReaderPosition(`later-${i}`, { page: 1, offset: 0 });
    }
    expect(countKeys(storage.keys(), SCROLL_PREFIX)).toBeLessThanOrEqual(1000);
    expect(readReaderPosition("legacy-7")).toBeNull();
    expect(readReaderPosition("later-1999")).toEqual({ page: 1, offset: 0 });
  });

  it("renews a chapter that is re-READ, not only one that is re-written", () => {
    // The reader writes a position when you leave a chapter and reads one when
    // you open it. A chapter opened every day but never scrolled would age out
    // under a least-recently-WRITTEN order -- and it is exactly the chapter
    // whose position is worth keeping.
    const limit = boundOnPositions(storage, "probe");

    writeReaderPosition("keep", { page: 7, offset: 70 });
    for (let i = 0; i < limit - 1; i += 1) {
      writeReaderPosition(`wave-a-${i}`, { page: 1, offset: 0 });
    }
    // The only thing that happens to "keep" from here on is being read.
    expect(readReaderPosition("keep")).toEqual({ page: 7, offset: 70 });
    for (let i = 0; i < limit - 1; i += 1) {
      writeReaderPosition(`wave-b-${i}`, { page: 1, offset: 0 });
    }

    expect(readReaderPosition("keep")).toEqual({ page: 7, offset: 70 });
  });

  it("is per profile: filling one profile's bound leaves another's positions alone", () => {
    setStorageScope(BOB);
    writeReaderPosition("bobs", { page: 3, offset: 30 });
    writePageRatios("bobs", [1.5]);

    setStorageScope(ALICE);
    for (let i = 0; i < 1500; i += 1) openChapter(i);

    setStorageScope(BOB);
    expect(readReaderPosition("bobs")).toEqual({ page: 3, offset: 30 });
    expect(readPageRatios("bobs")).toEqual([1.5]);
  });
});

describe("WS-4 writes survive a full quota", () => {
  it("a preference write that hits the quota makes room and lands", () => {
    const storage = installQuotaStorage(120_000);
    setStorageScope(ALICE);
    for (let i = 0; i < 1200; i += 1) openChapter(i);
    expect(storage.chars()).toBeLessThanOrEqual(120_000);
    storage.fill();

    writeScopedString("manhwamaniacs:reading-theme", "light");

    expect(readScopedString("manhwamaniacs:reading-theme")).toBe("light");
  });

  it("the reader still remembers the chapter being read after the quota is hit", () => {
    const storage = installQuotaStorage(120_000);
    setStorageScope(ALICE);
    for (let i = 0; i < 1200; i += 1) openChapter(i);
    storage.fill();

    writeReaderPosition("now", { page: 9, offset: 90 });
    writePageRatios("now", SHAPES);

    expect(readReaderPosition("now")).toEqual({ page: 9, offset: 90 });
    expect(readPageRatios("now")).toHaveLength(40);
  });

  it("gives up quietly when there is nothing to evict", () => {
    installQuotaStorage(10);
    setStorageScope(ALICE);

    expect(() => writeScopedString("manhwamaniacs:reading-theme", "light")).not.toThrow();
    expect(() => writeReaderPosition("now", { page: 9, offset: 90 })).not.toThrow();
    expect(readScopedString("manhwamaniacs:reading-theme")).toBeNull();
  });
});
