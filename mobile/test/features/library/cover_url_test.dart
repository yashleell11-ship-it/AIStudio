import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/library/utils/cover_url.dart';

void main() {
  group('seriesCoverUrl', () {
    test('builds cover URL from base and series id', () {
      expect(
        seriesCoverUrl('http://127.0.0.1:8000', 42),
        'http://127.0.0.1:8000/library/covers/42',
      );
    });

    test('normalizes trailing slash on base URL', () {
      expect(
        seriesCoverUrl('http://127.0.0.1:8000/', 7),
        'http://127.0.0.1:8000/library/covers/7',
      );
    });
  });
}
