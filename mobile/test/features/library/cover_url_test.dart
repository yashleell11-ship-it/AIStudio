import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/library/models/followed_series.dart';
import 'package:manhwamaniacs/features/library/utils/cover_url.dart';

FollowedSeries _series({required String coverUrl}) => FollowedSeries(
      id: 42,
      sourceId: 'asurascans',
      seriesKey: 'killer-pietro',
      title: 'Killer Pietro',
      coverUrl: coverUrl,
      isFavorite: false,
      readingStatus: 'reading',
      notify: false,
      sortOrder: 0,
      contentRating: 'safe',
      rating: 'safe',
      chapterCount: 10,
    );

void main() {
  group('followedSeriesCoverUrl', () {
    test('resolves a backend-relative proxy path against the API base', () {
      expect(
        followedSeriesCoverUrl(
          'http://127.0.0.1:8000',
          _series(coverUrl: '/sources/asurascans/series/killer-pietro/cover'),
        ),
        'http://127.0.0.1:8000/sources/asurascans/series/killer-pietro/cover',
      );
    });

    test('normalizes trailing slash on base URL', () {
      expect(
        followedSeriesCoverUrl(
          'http://127.0.0.1:8000/',
          _series(coverUrl: '/sources/asurascans/series/killer-pietro/cover'),
        ),
        'http://127.0.0.1:8000/sources/asurascans/series/killer-pietro/cover',
      );
    });

    test('leaves an absolute source cover URL untouched', () {
      expect(
        followedSeriesCoverUrl(
          'http://127.0.0.1:8000',
          _series(coverUrl: 'https://cdn.example.com/cover.jpg'),
        ),
        'https://cdn.example.com/cover.jpg',
      );
    });

    test('returns null for an empty cover URL', () {
      expect(
        followedSeriesCoverUrl('http://127.0.0.1:8000', _series(coverUrl: '')),
        isNull,
      );
    });
  });
}
