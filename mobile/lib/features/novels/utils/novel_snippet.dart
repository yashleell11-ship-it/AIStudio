/// Longest snippet stored with a novel bookmark. Enough to recognise a
/// passage, short enough that a screenful of bookmarks is still a small read
/// off the device. The same cap as `bookmark_service.SNIPPET_MAX_CHARS`, so a
/// snippet made offline and the one the server derives from its own cache are
/// the same length.
const int kNovelSnippetMaxChars = 180;

/// The prose at an exact bookmarked point, and whether the recorded paragraph
/// still exists.
///
/// This is what makes a bookmark in a wall of prose recognisable: a novel
/// bookmark has no cover, no page image and no page number worth reading, so
/// the words at that spot are the only thing that distinguishes it from every
/// other bookmark in the same chapter.
///
/// Starts **at the bookmarked point**, not at the paragraph's beginning —
/// snapped back to a word boundary and marked with a leading ellipsis so it
/// never reads as the start of the paragraph when it is not.
///
/// Degrades honestly: if the chapter's paragraph count has shrunk below
/// [anchorIndex], the nearest valid paragraph is used and the second return
/// value says so, rather than failing or silently showing the top of the
/// chapter.
///
/// A port of `services.bookmark_service.snippet_at` — the two clients and the
/// server show the same words for the same bookmark, or the offline copy and
/// the synced copy of one bookmark would look like two different bookmarks.
(String? snippet, bool stale) novelSnippetAt(
  List<String> paragraphs,
  int anchorIndex,
  double anchorFraction, {
  int maxChars = kNovelSnippetMaxChars,
}) {
  final total = paragraphs.length;
  if (total == 0) return (null, false);
  final wanted = anchorIndex < 1 ? 1 : anchorIndex;
  final index = wanted > total ? total : wanted;
  final stale = index != wanted;
  final text = paragraphs[index - 1].trim();
  if (text.isEmpty) return ('', stale);

  final fraction = anchorFraction.isNaN ? 0.0 : anchorFraction.clamp(0.0, 1.0);
  var start = (text.length * fraction).floor();
  if (start > text.length - 1) start = text.length - 1;
  if (start < 0) start = 0;
  if (start > 0) {
    final boundary = text.lastIndexOf(' ', start);
    start = boundary == -1 ? 0 : boundary + 1;
  }

  final end = start + maxChars;
  var excerpt = end >= text.length ? text.substring(start) : text.substring(start, end);
  if (text.length - start > maxChars) {
    final cut = excerpt.lastIndexOf(' ');
    if (cut > maxChars ~/ 2) excerpt = excerpt.substring(0, cut);
    excerpt = '${excerpt.trimRight()}…';
  }
  if (start > 0) excerpt = '…${excerpt.trimLeft()}';
  return (excerpt, stale);
}
