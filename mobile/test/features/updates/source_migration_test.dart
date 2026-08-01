import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/updates/models/source_migration.dart';
import 'package:manhwamaniacs/features/updates/utils/migration_plan_view.dart';
import 'package:manhwamaniacs/features/updates/utils/migration_ranking.dart';

/// Mirrors `frontend/src/features/updates/migration.test.ts`. The two clients
/// share the wording and the thresholds, so they should agree here too.
void main() {
  group('parseChapterOffset', () {
    test('empty means no offset', () {
      expect(parseChapterOffset(''), 0);
      expect(parseChapterOffset('   '), 0);
    });

    test('reads a signed decimal', () {
      expect(parseChapterOffset('12'), 12);
      expect(parseChapterOffset('-4.5'), -4.5);
    });

    test('garbage returns null so the caller refuses to preview', () {
      // Silently coercing to 0 would preview a different migration than the
      // one that was typed.
      expect(parseChapterOffset('abc'), isNull);
      expect(parseChapterOffset('1/2'), isNull);
    });

    test('non-finite input is rejected', () {
      expect(parseChapterOffset('Infinity'), isNull);
      expect(parseChapterOffset('NaN'), isNull);
    });
  });

  group('migrationTitleScore', () {
    test('identical titles score highest', () {
      expect(migrationTitleScore('Solo Leveling', 'Solo Leveling'), 4.0);
    });

    test('case and spacing are normalised away', () {
      expect(migrationTitleScore('  SOLO   Leveling ', 'solo leveling'), 4.0);
    });

    test('a contained query outranks merely sharing words', () {
      final contained = migrationTitleScore('Solo Leveling Ragnarok', 'Solo Leveling');
      final shared = migrationTitleScore('Leveling Alone Solo', 'Solo Leveling');
      expect(contained, greaterThan(shared));
    });

    test('nothing in common scores zero', () {
      expect(migrationTitleScore('Tower of God', 'Solo Leveling'), 0.0);
    });
  });

  group('MigrationTitleMatch', () {
    test('maps scores onto the documented bands', () {
      expect(MigrationTitleMatch.ofScore(4.0), MigrationTitleMatch.exact);
      expect(MigrationTitleMatch.ofScore(3.0), MigrationTitleMatch.contains);
      expect(MigrationTitleMatch.ofScore(2.0), MigrationTitleMatch.allWords);
      expect(MigrationTitleMatch.ofScore(1.5), MigrationTitleMatch.someWords);
      expect(MigrationTitleMatch.ofScore(0.0), MigrationTitleMatch.unrelated);
    });
  });

  group('rankMigrationCandidates', () {
    MigrationCandidate candidate(String title, {int? chapters}) =>
        MigrationCandidate(
          source: 'src-$title',
          seriesId: 'id-$title',
          title: title,
          chapterCount: chapters,
        );

    test('preserves the server order rather than re-sorting', () {
      // The server already demotes unhealthy connectors; re-sorting here would
      // undo that and float ~100 dead sources back up.
      final ranked = rankMigrationCandidates(
        [candidate('Zzz Unrelated'), candidate('Solo Leveling')],
        followedTitle: 'Solo Leveling',
        knownChapterCount: 0,
      );

      expect(ranked.map((r) => r.candidate.title),
          ['Zzz Unrelated', 'Solo Leveling']);
    });

    test('flags a target that would lose the tail', () {
      final ranked = rankMigrationCandidates(
        [candidate('Solo Leveling', chapters: 90)],
        followedTitle: 'Solo Leveling',
        knownChapterCount: 100,
      );

      expect(ranked.single.chapterShortfall, 10);
      expect(ranked.single.losesTail, isTrue);
    });

    test('a never-checked tracker yields no shortfall rather than a bogus one', () {
      final ranked = rankMigrationCandidates(
        [candidate('Solo Leveling', chapters: 90)],
        followedTitle: 'Solo Leveling',
        knownChapterCount: 0,
      );

      expect(ranked.single.chapterShortfall, isNull);
      expect(ranked.single.losesTail, isFalse);
    });

    test('a target with more chapters does not lose the tail', () {
      final ranked = rankMigrationCandidates(
        [candidate('Solo Leveling', chapters: 120)],
        followedTitle: 'Solo Leveling',
        knownChapterCount: 100,
      );

      expect(ranked.single.losesTail, isFalse);
    });
  });

  group('migrationSummary', () {
    test('says plainly when nothing is left behind', () {
      const counts = MigrationCounts(
        oldTotal: 10,
        newTotal: 12,
        matched: 10,
        dropped: 0,
      );

      expect(migrationSummary(counts), contains('nothing is left behind'));
    });

    test('names the chapters that cannot be carried', () {
      const counts = MigrationCounts(
        oldTotal: 10,
        newTotal: 12,
        matched: 9,
        dropped: 1,
      );

      final summary = migrationSummary(counts);
      expect(summary, contains('9'));
      expect(summary, contains('12'));
      expect(summary, contains('cannot be carried over'));
    });
  });

  group('ChapterMapEntry.carriesOver', () {
    test('an entry with a target carries over', () {
      const entry = ChapterMapEntry(
        fromChapterId: 'a',
        number: 1,
        toChapterId: 'b',
        match: ChapterMatch.exact,
      );

      expect(entry.carriesOver, isTrue);
    });

    test('an unmatched entry does not', () {
      const entry = ChapterMapEntry(
        fromChapterId: 'a',
        number: null,
        toChapterId: null,
        match: ChapterMatch.none,
      );

      expect(entry.carriesOver, isFalse);
    });
  });

  group('oldCatalogLabel', () {
    test('distinguishes a readable old source from a cached or dead one', () {
      expect(oldCatalogLabel(OldCatalogState.ok), isNot(
          oldCatalogLabel(OldCatalogState.unavailable)));
      expect(oldCatalogLabel(OldCatalogState.cached), isNot(
          oldCatalogLabel(OldCatalogState.unavailable)));
    });
  });
}
