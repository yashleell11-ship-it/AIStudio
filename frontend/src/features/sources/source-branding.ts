/** Client-side favicon fallbacks when the API omits icon_url. */
const FAVICON_BY_SOURCE: Record<string, string> = {
  mangadex: "https://mangadex.org/favicon.ico",
  toonily: "https://toonily.com/favicon.ico",
  asura: "https://asuracomic.net/favicon.ico",
  asurascans: "https://asuracomic.net/favicon.ico",
  mangakatana: "https://mangakatana.com/favicon.ico",
  webtoons: "https://www.webtoons.com/favicon.ico",
  comick: "https://comick.io/favicon.ico",
  bato: "https://bato.to/favicon.ico",
  bbato: "https://bato.to/favicon.ico",
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
