const ENABLED = process.env.NODE_ENV === "development";

export function readerDebug(event: string, data?: Record<string, unknown>): void {
  if (!ENABLED) return;
  console.info(`[reader] ${event}`, data ?? "");
}
