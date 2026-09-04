/** Client-side favicon fallbacks when the API omits icon_url. */
const FAVICON_BY_SOURCE: Record<string, string> = {
  mangadex: "https://mangadex.org/favicon.ico",
  toonily: "https://toonily.com/favicon.ico",
  asura: "https://asuracomic.net/favicon.ico",
  asurascans: "https://asuracomic.net/favicon.ico",
  mangakatana: "https://mangakatana.com/favicon.ico",
  webtoons: "https://www.webtoons.com/favicon.ico",
  tapas: "https://tapas.io/favicon.ico",
  comick: "https://comick.io/favicon.ico",
  bato: "https://bato.to/favicon.ico",
  manganelo: "https://manganelo.com/favicon.ico",
  manganato: "https://manganato.com/favicon.ico",
  reaperscans: "https://reaperscans.com/favicon.ico",
  flamescans: "https://flamescans.org/favicon.ico",
  luminousscans: "https://luminousscans.com/favicon.ico",
  nhentai: "https://nhentai.net/favicon.ico",
  aurorascans: "https://qimanga.com/favicon.ico",
};

export function sourceFaviconUrl(sourceId: string): string | null {
  return FAVICON_BY_SOURCE[sourceId.toLowerCase()] ?? null;
}

/**
 * Best-effort display name for a source id, used when the resolved
 * {@link SourceSummary} name isn't available (e.g. the sources list is still
 * loading, or a federated hit references a source not in the list). Just
 * capitalizes the id — `"mangadex"` → `"Mangadex"`.
 */
export function prettifySourceId(sourceId: string): string {
  return sourceId.length === 0
    ? sourceId
    : sourceId[0].toUpperCase() + sourceId.slice(1);
}
