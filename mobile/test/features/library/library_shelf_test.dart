import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/library/models/followed_series.dart';
import 'package:manhwamaniacs/features/library/utils/library_shelf.dart';

FollowedSeries _series({
  int id = 1,
  String title = 'The Count of Monte Cristo',
  String coverUrl = '',
  bool isFavorite = false,
  String readingStatus = 'reading',
  int chapterCount = 117,
}) {
  return FollowedSeries(
    id: id,
    sourceId: 'gutendex',
    seriesKey: 'monte-cristo',
    title: title,
    coverUrl: coverUrl,
    isFavorite: isFavorite,
    readingStatus: readingStatus,
    notify: false,
    sortOrder: 0,
    contentRating: 'safe',
    rating: 'safe',
    chapterCount: chapterCount,
  );
}

void main() {
  group('libraryShelfBook', () {
    test('says only what a follow row actually knows', () {
      final book = libraryShelfBook(
        _series(),
        apiBaseUrl: 'http://127.0.0.1:8000',
        onTap: () {},
      );

      // Author, blurb and publication status live on the source, not on the
      // follow — inventing them is how a shelf starts lying.
      expect(book.author, isNull);
      expect(book.description, isNull);
      expect(book.status, isNull);
      expect(book.title, 'The Count of Monte Cristo');
      expect(book.chapterCount, 117);
    });

    test('resolves a backend-relative cover against the API base', () {
      final book = libraryShelfBook(
        _series(coverUrl: '/sources/gutendex/series/monte-cristo/cover'),
        apiBaseUrl: 'http://127.0.0.1:8000',
        onTap: () {},
      );

      expect(
        book.coverUrl,
        'http://127.0.0.1:8000/sources/gutendex/series/monte-cristo/cover',
      );
    });

    test('passes null rather than an empty cover, so the row draws a plate', () {
      final book = libraryShelfBook(
        _series(),
        apiBaseUrl: 'http://127.0.0.1:8000',
        onTap: () {},
      );

      expect(book.coverUrl, isNull);
    });

    test('carries the library state the row has to keep showing', () {
      final book = libraryShelfBook(
        _series(isFavorite: true),
        apiBaseUrl: 'http://127.0.0.1:8000',
        onTap: () {},
        onLongPress: () {},
        note: readingStatusNote('plan_to_read'),
        selected: true,
        unreadCount: 3,
      );

      expect(book.isFavorite, isTrue);
      expect(book.selected, isTrue);
      expect(book.unreadCount, 3);
      expect(book.onLongPress, isNotNull);
    });

    test('a browse-shelf row is unselected, unmarked and has no menu', () {
      final book = libraryShelfBook(
        _series(),
        apiBaseUrl: 'http://127.0.0.1:8000',
        onTap: () {},
      );

      expect(book.selected, isFalse);
      expect(book.unreadCount, 0);
      expect(book.onLongPress, isNull);
    });

    test('sets the metadata line to length then shelf mark, in that order', () {
      final book = libraryShelfBook(
        _series(),
        apiBaseUrl: 'http://127.0.0.1:8000',
        onTap: () {},
        note: readingStatusNote('reading'),
      );

      expect(book.metaParts, ['117 chapters', 'Reading']);
    });

    test('drops the chapter count the update checker has not populated', () {
      // 0 until the backend's first update check runs. "0 chapters" would be
      // a lie, so the row says nothing about length at all.
      final book = libraryShelfBook(
        _series(chapterCount: 0),
        apiBaseUrl: 'http://127.0.0.1:8000',
        onTap: () {},
        note: readingStatusNote('unread'),
      );

      expect(book.metaParts, ['Unread']);
    });
  });

  group('readingStatusNote', () {
    test('unwraps the wire form and capitalises it for a metadata run', () {
      expect(readingStatusNote('plan_to_read'), 'Plan to read');
      expect(readingStatusNote('reading'), 'Reading');
      expect(readingStatusNote('completed'), 'Completed');
    });

    test('is null for a status the server did not set', () {
      expect(readingStatusNote(''), isNull);
      expect(readingStatusNote('   '), isNull);
    });
  });

  group('latestChapterNote', () {
    test('labels the newest chapter the profile was notified about', () {
      expect(latestChapterNote('Chapter 121'), 'Latest: Chapter 121');
    });

    test('is null for a book that has never produced a notification', () {
      expect(latestChapterNote(null), isNull);
      expect(latestChapterNote(''), isNull);
    });
  });
}
