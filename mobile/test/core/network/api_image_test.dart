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
      // No token means no request identity at all — a profile id alone never
      // produces headers.
      expect(apiImageHttpHeaders(null, profileId: 3), isNull);
    });

    test('attaches X-Profile-Id so the image proxy resolves the same 18+ gate '
        'as the JSON routes', () {
      expect(
        apiImageHttpHeaders('secret-token', profileId: 7),
        {'Authorization': 'Bearer secret-token', 'X-Profile-Id': '7'},
      );
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
