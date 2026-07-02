export interface ChapterLabel {
  primary: string;
  secondary: string | null;
}

/**
 * Display label for a source chapter. The canonical chapter number always
 * leads; the source-provided title is separate metadata shown beneath it.
 * Only when a source has no chapter number does the title become the label.
 */
export function chapterLabel(chapter: {
  number: number | null;
  title: string | null;
}): ChapterLabel {
  const title = chapter.title?.trim() ?? "";
  if (chapter.number == null) {
    return { primary: title || "Chapter", secondary: null };
  }
  const primary = `Chapter ${chapter.number}`;
  return { primary, secondary: dedupeTitle(title, primary) };
}

/**
 * Sources often embed the chapter number in the title ("Chapter 134", or
 * "Chapter 12: The Hunt"). The number line already shows it, so drop the
 * redundant prefix — but never a decimal continuation ("Chapter 12.5").
 */
function dedupeTitle(title: string, primary: string): string | null {
  if (!title) {
    return null;
  }
  if (title.toLowerCase().startsWith(primary.toLowerCase())) {
    const rest = title.slice(primary.length);
    if (rest === "") {
      return null;
    }
    const separator = rest.match(/^\s*[:\-–—]\s*|^\s+/);
    if (separator) {
      return rest.slice(separator[0].length).trim() || null;
    }
  }
  return title;
}
