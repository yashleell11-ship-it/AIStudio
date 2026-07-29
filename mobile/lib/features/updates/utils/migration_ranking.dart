import 'package:manhwamaniacs/features/updates/models/source_migration.dart';

/// Ranking of source-migration candidates: how confidently each one is the same
/// series, and what moving there would cost.
///
/// The ORDER is the server's and is preserved verbatim. `migration-candidates`
/// returns one candidate per source in federated-search group order, and that
/// order is already this candidate's own relevance: a group's sort score *is*
/// its best item's score (`browse_service.py:697`), groups sort by
/// `(demoted, -score, has_items, name)` (`:805-812`), and a group with no items
/// never becomes a candidate at all (`update_service.py:649-653`). Re-sorting
/// client-side could only undo the health demotion that keeps the ~100 dead
/// connectors out of the way, so this ranks by *labelling*, not by reordering —
/// the same rule `source_search_group.dart` already states for search results.
///
/// What the client does have to compute is the score itself: the endpoint drops
/// it from the payload, and on a phone the owner sees three candidates at a time
/// and needs to know whether the top hit is actually the series they follow.
/// [migrationTitleScore] is a port of the backend's `_relevance_score`
/// (`browse_service.py:93-113`), not a second scoring model.

/// Tier of [migrationTitleScore], for a badge the owner can read at a glance.
enum MigrationTitleMatch {
  /// Titles are identical once whitespace and case are normalised.
  exact,

  /// The followed title appears whole inside the candidate's title — the usual
  /// shape of a season/part suffix.
  contains,

  /// Every word of the followed title appears somewhere in the candidate's.
  allWords,

  /// Some words matched. Worth a look, worth a second glance.
  someWords,

  /// No literal overlap. That means "no shared words", NOT "wrong series":
  /// connectors normalise away the alternative titles a site matched on, so a
  /// zero-scoring hit can still be the right one.
  unrelated;

  /// The tier a raw [migrationTitleScore] falls in.
  static MigrationTitleMatch ofScore(double score) {
    if (score >= 4.0) return MigrationTitleMatch.exact;
    if (score >= 3.0) return MigrationTitleMatch.contains;
    if (score >= 2.0) return MigrationTitleMatch.allWords;
    if (score > 0.0) return MigrationTitleMatch.someWords;
    return MigrationTitleMatch.unrelated;
  }

  /// Short badge text. Null for [unrelated] and [someWords]-and-better tiers
  /// that would only add noise — see the callers for which are shown.
  String get label => switch (this) {
        MigrationTitleMatch.exact => 'Exact title',
        MigrationTitleMatch.contains => 'Close title',
        MigrationTitleMatch.allWords => 'All words',
        MigrationTitleMatch.someWords => 'Partial title',
        MigrationTitleMatch.unrelated => 'Different title',
      };
}

final RegExp _whitespace = RegExp(r'\s+');
final RegExp _tokenSplit = RegExp(r'[^\w]+', unicode: true);

/// Collapse whitespace and casefold — the backend's `_normalize_title`
/// (`browse_service.py:84-86`).
String normalizeSeriesTitle(String title) =>
    title.trim().replaceAll(_whitespace, ' ').toLowerCase();

List<String> _tokens(String query) => [
      for (final token in query.toLowerCase().split(_tokenSplit))
        if (token.isNotEmpty) token,
    ];

/// Score [title] against [query]. `0.0` means "shares nothing".
///
/// Port of `_relevance_score` (`browse_service.py:93-113`) — same tiers, same
/// numbers — so a candidate's client-side badge cannot disagree with the server
/// order it arrived in.
double migrationTitleScore(String title, String query) {
  final normalized = normalizeSeriesTitle(title);
  final queryNorm = normalizeSeriesTitle(query);
  final tokens = _tokens(query);
  if (normalized.isEmpty || tokens.isEmpty) return 0.0;
  if (normalized == queryNorm) return 4.0;
  if (queryNorm.isNotEmpty && normalized.contains(queryNorm)) return 3.0;
  final matched = tokens.where(normalized.contains).length;
  if (matched == tokens.length) return 2.0;
  if (matched > 0) return 1.0 + matched / tokens.length;
  return 0.0;
}

/// A candidate plus the two things the payload does not carry: how well its
/// title matches the follow, and whether its catalog is visibly smaller.
class RankedMigrationCandidate {
  const RankedMigrationCandidate({
    required this.candidate,
    required this.titleMatch,
    required this.chapterShortfall,
  });

  final MigrationCandidate candidate;
  final MigrationTitleMatch titleMatch;

  /// How many chapters the target is missing relative to what the follow
  /// already knows about, or null when the source did not report a count.
  ///
  /// Advisory only, and deliberately shown *before* a dry run: the authoritative
  /// answer needs a scraper round-trip per candidate, and on a phone that is a
  /// slow, cellular, one-at-a-time cost. Zero or negative means "not smaller".
  final int? chapterShortfall;

  /// True when the target is known to have fewer chapters than the follow —
  /// progress above the target's last chapter cannot come along.
  bool get losesTail => (chapterShortfall ?? 0) > 0;
}

/// Annotate [candidates] in place — same list, same order, one tier and one
/// shortfall each.
///
/// [followedTitle] is the tracker's title (what the query defaults to) and
/// [knownChapterCount] the tracker's `known_chapter_count`, which is 0 until the
/// first successful update check; 0 yields a null shortfall rather than a
/// meaningless "the target has 400 extra chapters".
List<RankedMigrationCandidate> rankMigrationCandidates(
  List<MigrationCandidate> candidates, {
  required String followedTitle,
  required int knownChapterCount,
}) {
  return [
    for (final candidate in candidates)
      RankedMigrationCandidate(
        candidate: candidate,
        titleMatch: MigrationTitleMatch.ofScore(
          migrationTitleScore(candidate.title, followedTitle),
        ),
        chapterShortfall:
            (candidate.chapterCount == null || knownChapterCount <= 0)
                ? null
                : knownChapterCount - candidate.chapterCount!,
      ),
  ];
}
