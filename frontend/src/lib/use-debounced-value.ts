"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * A value that only settles once it has stopped changing.
 *
 * For an input that keys a NETWORK request, not for cosmetics: React's own
 * `useDeferredValue` lowers a render's priority, it does not delay anything, so
 * every keystroke would still produce a distinct query key and a distinct
 * fetch. This holds the value back in wall-clock time, which is the only thing
 * that stops the request.
 *
 * `flush` commits the pending value immediately, for the moments the user has
 * plainly finished typing — pressing Enter, or picking a suggestion — so the
 * delay is only ever paid mid-word.
 */
export function useDebouncedValue<T>(value: T, delayMs: number): [T, () => void] {
  const [settled, setSettled] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  // Closes over the value of the render it was made in, which is the current
  // one at the moment any handler calling it fires.
  const flush = useCallback(() => setSettled(value), [value]);

  return [settled, flush];
}
