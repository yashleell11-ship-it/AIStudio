export interface SnippetSegment {
  text: string;
  highlight: boolean;
}

/**
 * Parse a server-highlighted OCR snippet into safe segments.
 *
 * The backend wraps matched terms in literal `<mark>…</mark>` markers inside
 * otherwise-plain OCR text. Rendering that as HTML would be an XSS vector, so
 * instead we split it into `{ text, highlight }` runs and let React render each
 * run as an escaped text node — the highlight is applied with a real `<mark>`
 * element in the component, never via `dangerouslySetInnerHTML`.
 *
 * Unbalanced or nested markers degrade gracefully to plain text.
 */
export function parseSnippet(snippet: string): SnippetSegment[] {
  const segments: SnippetSegment[] = [];
  const pattern = /<mark>([\s\S]*?)<\/mark>/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(snippet)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ text: snippet.slice(lastIndex, match.index), highlight: false });
    }
    if (match[1].length > 0) {
      segments.push({ text: match[1], highlight: true });
    }
    lastIndex = pattern.lastIndex;
  }

  if (lastIndex < snippet.length) {
    segments.push({ text: snippet.slice(lastIndex), highlight: false });
  }

  return segments;
}
