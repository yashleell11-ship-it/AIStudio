import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/app/router/routes.dart';

void main() {
  group('isMainTabRoute', () {
    test('true on tab roots', () {
      expect(isMainTabRoute(Routes.library), isTrue);
      expect(isMainTabRoute(Routes.sources), isTrue);
      expect(isMainTabRoute(Routes.downloads), isTrue);
      expect(isMainTabRoute(Routes.search), isTrue);
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
}
