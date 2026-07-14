import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/network/api_image.dart';

void main() {
  group('apiImageHttpHeaders', () {
    test('returns Authorization header when token is present', () {
      expect(
        apiImageHttpHeaders('secret-token'),
        {'Authorization': 'Bearer secret-token'},
      );
    });

    test('returns null for empty or missing token', () {
      expect(apiImageHttpHeaders(null), isNull);
      expect(apiImageHttpHeaders(''), isNull);
    });
  });

  group('resolveApiResourceUrl', () {
    const base = 'https://app.manhwamaniacs.xyz';

    test('passes through absolute URLs unchanged', () {
      expect(
        resolveApiResourceUrl(base, 'https://cdn.example.com/cover.webp'),
        'https://cdn.example.com/cover.webp',
      );
    });

    test('joins relative API paths without double slashes', () {
      expect(
        resolveApiResourceUrl(
          base,
          '/sources/asurascans/series/foo/cover',
        ),
        'https://app.manhwamaniacs.xyz/sources/asurascans/series/foo/cover',
      );
    });

    test('normalizes trailing slash on base URL', () {
      expect(
        resolveApiResourceUrl(
          '$base/',
          '/sources/asurascans/series/foo/cover',
        ),
        'https://app.manhwamaniacs.xyz/sources/asurascans/series/foo/cover',
      );
    });
  });
}
