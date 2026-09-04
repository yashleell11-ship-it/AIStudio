import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/app/router/routes.dart';

void main() {
  group('isMainTabRoute', () {
    test('true on tab roots', () {
      expect(isMainTabRoute(Routes.library), isTrue);
      expect(isMainTabRoute(Routes.sources), isTrue);
      expect(isMainTabRoute(Routes.search), isTrue);
      // Downloads joined the tab bar; without this the shell hides the
      // navigation bar on its own tab.
      expect(isMainTabRoute(Routes.downloads), isTrue);
      expect(isMainTabRoute(Routes.more), isTrue);
    });

    test('false on nested browse and detail routes', () {
      expect(isMainTabRoute('/sources/asurascans'), isFalse);
      expect(
        isMainTabRoute('/sources/asurascans/series/foo-bar'),
        isFalse,
      );
      expect(isMainTabRoute('/library/browse'), isFalse);
      expect(isMainTabRoute('/library/42'), isFalse);
    });
  });

  group('Read all (spec R2)', () {
    test('is the ordinary reader path plus a flag, not a route of its own', () {
      final ordinary = RoutePaths.reader('asura', 'solo-leveling', 'ch-1');
      final all = RoutePaths.readAll('asura', 'solo-leveling', 'ch-1');
      // Every deep link, bookmark and resume into the ordinary reader has to
      // keep working untouched, which is why this is a query flag.
      expect(all, startsWith(ordinary));
      expect(all, '$ordinary?all=1');
    });

    test('the source-browse reader gets the same flag', () {
      final ordinary =
          RoutePaths.sourceReader('asura', 'solo-leveling', 'ch-1');
      expect(
        RoutePaths.sourceReadAll('asura', 'solo-leveling', 'ch-1'),
        '$ordinary?all=1',
      );
    });

    test('a slash-bearing chapter key survives the flag', () {
      // Madara-family keys look like `series-slug/chapter-3`; the whole key is
      // one percent-encoded segment and the flag must not disturb that.
      final path = RoutePaths.readAll(
        'toonily',
        'series/solo-leveling',
        'series/solo-leveling/chapter-3',
      );
      expect(path, contains('series%2Fsolo-leveling%2Fchapter-3'));
      expect(Uri.parse(path).queryParameters['all'], '1');
    });

    test('the flag is a request, not a protocol', () {
      expect(isReadAllRequest(const {'all': '1'}), isTrue);
      expect(isReadAllRequest(const {'all': 'true'}), isTrue);
      expect(isReadAllRequest(const {'all': 'TRUE'}), isTrue);
      // A bare `?all` round-trips as an empty value.
      expect(isReadAllRequest(const {'all': ''}), isTrue);

      expect(isReadAllRequest(const {}), isFalse);
      expect(isReadAllRequest(const {'page': '4'}), isFalse);
      expect(isReadAllRequest(const {'all': '0'}), isFalse);
      expect(isReadAllRequest(const {'all': 'false'}), isFalse);
    });

    test('Read-all and a resume page coexist in one query', () {
      final path = '${RoutePaths.readAll('asura', 'sl', 'ch-9')}&page=7';
      final uri = Uri.parse(path);
      expect(isReadAllRequest(uri.queryParameters), isTrue);
      expect(uri.queryParameters['page'], '7');
    });
  });
}
