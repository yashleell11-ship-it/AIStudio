/**
 * Subsequence fuzzy matching for the command palette.
 *
 * Deliberately not a generic string-distance metric: the palette is judged on
 * "I typed `dl` and Downloads came first", which is a *subsequence* question,
 * not an edit-distance one. Levenshtein would rank `Downloads` below any
 * two-character title and would never let `sl` find "Solo Levelling".
 *
 * The alignment is found by dynamic programming rather than by scanning greedily
 * left-to-right, because the leftmost match is routinely the wrong one: greedy
 * matching of `sl` against "Solo Levelling" takes the `l` of "So**l**o" and
 * scores (and highlights) an initialism as if it were noise. The DP is O(query x
 * text) over strings that are a title long, which is nothing per keystroke.
 *
 * Weights follow fzf's shape — a large per-character score with comparatively
 * small positional bonuses — so that matching MORE of the query always beats
 * matching less of it in a prettier place. Absolute values are meaningless; only
 * the ordering they produce matters.
 */

/** A match, with the indices of `text` that the query consumed (for highlighting). */
export interface FuzzyMatch {
  score: number;
  /** Indices into the ORIGINAL text, ascending. */
  indices: number[];
}

const SCORE_MATCH = 16;
/** First character of a word — the strongest positional signal. */
const BONUS_BOUNDARY = 8;
/** `camelCase` hump; slightly weaker than a real word break. */
const BONUS_CAMEL = 7;
/** Immediately after the previous matched character. */
const BONUS_CONSECUTIVE = 8;
/** The first matched character's bonus counts double. */
const BONUS_FIRST_CHAR = 2;
/** Opening any gap between two matched characters. */
const GAP_START = -3;
/** Each additional character inside that gap. */
const GAP_EXTENSION = -1;
/**
 * Per character of `text` skipped before the FIRST match. Small and fractional:
 * it only has to break ties between two otherwise identical matches, so that
 * "Library" outranks "My Library" without ever outweighing a real bonus.
 */
const PENALTY_LEADING = 0.5;

const WORD_SEPARATORS = new Set([" ", "-", "_", "/", ":", ".", ",", "(", "[", "'"]);

/** How good a place `index` is to start matching at, ignoring what precedes it. */
function positionBonus(text: string, index: number): number {
  if (index === 0) return BONUS_BOUNDARY;
  if (WORD_SEPARATORS.has(text[index - 1])) return BONUS_BOUNDARY;
  const previous = text[index - 1];
  const current = text[index];
  if (previous === previous.toLowerCase() && current !== current.toLowerCase()) {
    return BONUS_CAMEL;
  }
  if (/[0-9]/.test(current) && !/[0-9]/.test(previous)) return BONUS_CAMEL;
  return 0;
}

const NO_MATCH = Number.NEGATIVE_INFINITY;

/**
 * Score `query` against `text`, or `null` when `text` does not contain the
 * query's characters in order.
 *
 * An empty query matches everything with score 0, which lets callers use one
 * path for the "nothing typed yet" listing.
 */
export function fuzzyMatch(query: string, text: string): FuzzyMatch | null {
  const needle = query.trim().toLowerCase();
  if (needle.length === 0) return { score: 0, indices: [] };
  if (needle.length > text.length) return null;

  const haystack = text.toLowerCase();
  const rows = needle.length;
  const columns = text.length;

  // `scores[j]` is the best score for a match of the current query character
  // ENDING at text index j; `previous` is the same for the character before it.
  let previous = new Float64Array(columns).fill(NO_MATCH);
  let scores = new Float64Array(columns);
  // `from[i][j]` is the text index the previous query character matched at, for
  // the best alignment ending at (i, j). -1 marks the start of the alignment.
  const from: Int32Array[] = [];

  for (let i = 0; i < rows; i += 1) {
    scores = new Float64Array(columns).fill(NO_MATCH);
    const predecessors = new Int32Array(columns).fill(-1);

    // Running best of `previous[k] - GAP_EXTENSION * k` over all k <= j - 2 —
    // the algebraic rearrangement that turns "max over every earlier column"
    // into O(1) per column. Only columns at distance >= 2 qualify; distance 1 is
    // the consecutive case, handled separately with its own bonus.
    let gapBest = NO_MATCH;
    let gapBestIndex = -1;

    for (let j = 0; j < columns; j += 1) {
      if (j >= 2) {
        const candidate = j - 2;
        const value = previous[candidate];
        if (value !== NO_MATCH) {
          const shifted = value - GAP_EXTENSION * candidate;
          if (shifted > gapBest) {
            gapBest = shifted;
            gapBestIndex = candidate;
          }
        }
      }

      if (haystack[j] !== needle[i]) continue;

      const bonus = positionBonus(text, j);

      if (i === 0) {
        scores[j] = SCORE_MATCH + bonus * BONUS_FIRST_CHAR - PENALTY_LEADING * j;
        continue;
      }

      let best = NO_MATCH;
      let bestFrom = -1;

      // Directly after the previous matched character.
      if (j >= 1 && previous[j - 1] !== NO_MATCH) {
        best =
          previous[j - 1] + SCORE_MATCH + Math.max(BONUS_CONSECUTIVE, bonus);
        bestFrom = j - 1;
      }

      // Separated from it by at least one character.
      if (gapBestIndex !== -1) {
        const gapped =
          gapBest +
          GAP_START +
          GAP_EXTENSION * (j - 2) +
          SCORE_MATCH +
          bonus;
        if (gapped > best) {
          best = gapped;
          bestFrom = gapBestIndex;
        }
      }

      if (best === NO_MATCH) continue;
      scores[j] = best;
      predecessors[j] = bestFrom;
    }

    from.push(predecessors);
    previous = scores;
  }

  // Best alignment of the whole query = best cell in the last row.
  let endIndex = -1;
  let bestScore = NO_MATCH;
  for (let j = 0; j < columns; j += 1) {
    if (scores[j] > bestScore) {
      bestScore = scores[j];
      endIndex = j;
    }
  }
  if (endIndex === -1 || bestScore === NO_MATCH) return null;

  const indices = new Array<number>(rows);
  let cursor = endIndex;
  for (let i = rows - 1; i >= 0; i -= 1) {
    indices[i] = cursor;
    cursor = from[i][cursor];
  }

  return { score: bestScore, indices };
}

/**
 * Best score for `query` across several haystacks — a command's title plus its
 * subtitle and keywords. Only the primary text's indices are returned, so a
 * keyword hit highlights nothing rather than highlighting the wrong characters.
 */
export function fuzzyMatchAny(
  query: string,
  primary: string,
  secondary: readonly string[] = [],
): FuzzyMatch | null {
  const primaryMatch = fuzzyMatch(query, primary);
  let best = primaryMatch;

  for (const text of secondary) {
    const match = fuzzyMatch(query, text);
    if (match === null) continue;
    // Secondary text is a weaker signal than the visible title: a keyword hit
    // must not push a command above one whose own name matched.
    const scaled = { score: match.score * 0.6, indices: primaryMatch?.indices ?? [] };
    if (best === null || scaled.score > best.score) best = scaled;
  }

  return best;
}

/**
 * Split `text` into alternating unmatched/matched runs for rendering, starting
 * with an unmatched run (possibly empty). Keeps highlight logic out of JSX.
 */
export function highlightSegments(
  text: string,
  indices: readonly number[],
): { text: string; match: boolean }[] {
  if (indices.length === 0) return [{ text, match: false }];

  const marked = new Set(indices);
  const segments: { text: string; match: boolean }[] = [];
  let current = "";
  let currentMatch = marked.has(0);

  for (let i = 0; i < text.length; i += 1) {
    const isMatch = marked.has(i);
    if (isMatch !== currentMatch) {
      segments.push({ text: current, match: currentMatch });
      current = "";
      currentMatch = isMatch;
    }
    current += text[i];
  }
  segments.push({ text: current, match: currentMatch });

  return segments;
}
