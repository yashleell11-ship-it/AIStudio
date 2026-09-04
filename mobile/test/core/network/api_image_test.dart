import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/network/api_image.dart';

void main() {
  group('apiImageHttpHeaders', () {
    test('returns Authorization header when token is present', () {
      expect(
        apiImageHttpHeaders('secret-token'),
        {
          'Authorization': 'Bearer secret-token',
          'Accept': 'image/webp,image/jpeg,*/*',
        },
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
        {
          'Authorization': 'Bearer secret-token',
          'Accept': 'image/webp,image/jpeg,*/*',
          'X-Profile-Id': '7',
        },
      );
    });

    test('names image/webp literally, because the proxy ignores a bare */*',
        () {
      final accept = apiImageHttpHeaders('secret-token')!['Accept']!;
      expect(accept.split(',').map((part) => part.trim()), contains('image/webp'));
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

  group('coverRequestWidth', () {
    test('converts a logical slot width to device pixels', () {
      expect(coverRequestWidth(120, 3), 360);
      expect(coverRequestWidth(64, 2), 128);
      expect(coverRequestWidth(117.5, 2), 235);
    });

    test('clamps to the ceiling rather than asking for a poster', () {
      expect(coverRequestWidth(400, 3), kMaxCoverRequestWidth);
      expect(coverRequestWidth(2048, 2), kMaxCoverRequestWidth);
    });

    test('returns null for a slot that has no usable width', () {
      // An unbounded or absent width means "serve the original" — never an
      // exception, and never a NaN in a URL.
      expect(coverRequestWidth(null, 3), isNull);
      expect(coverRequestWidth(double.infinity, 3), isNull);
      expect(coverRequestWidth(double.nan, 3), isNull);
      expect(coverRequestWidth(0, 3), isNull);
      expect(coverRequestWidth(-40, 3), isNull);
      expect(coverRequestWidth(120, 0), isNull);
    });
  });

  group('coverUrlAtWidth', () {
    const proxy = 'https://app.manhwamaniacs.xyz/sources/mangadex/series/orv/cover';

    test('adds ?w= to the backend cover proxy', () {
      expect(coverUrlAtWidth(proxy, 360), '$proxy?w=360');
    });

    test('leaves a source\'s own absolute cover URL untouched', () {
      // The same field carries third-party CDN links, some of them signed.
      const cdn = 'https://uploads.mangadex.org/covers/abc/def.jpg?token=xyz';
      expect(coverUrlAtWidth(cdn, 360), cdn);
    });

    test('is a no-op without a width', () {
      expect(coverUrlAtWidth(proxy, null), proxy);
    });

    test('never doubles up on a URL that already carries a width', () {
      expect(coverUrlAtWidth(coverUrlAtWidth(proxy, 360), 480), '$proxy?w=360');
    });

    test('leaves an empty URL alone', () {
      expect(coverUrlAtWidth('', 360), '');
    });
  });
}
