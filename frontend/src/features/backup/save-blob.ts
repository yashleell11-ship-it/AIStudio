/**
 * Hand bytes already in memory to the browser's downloader.
 *
 * The export is fetched rather than linked to (the session cookie would not
 * survive a browser-managed request — see `services/http.ts`), so by the time
 * the user gets a file it is a `Blob`, and the only way to offer it as a
 * download is a temporary object URL behind a synthetic anchor.
 */
export function saveBlobAsFile(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = "noopener";
  // Firefox only acts on a click if the anchor is in the document.
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  // Revoking in the same tick cancels the download it was created for; the
  // browser has taken the URL by the time the task queue drains.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
