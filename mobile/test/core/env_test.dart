import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/config/env.dart';

void main() {
  group('Env.hasBakedProductionUrl', () {
    test('is false for default dev compile-time URL', () {
      // flutter test without --dart-define uses defaults (dev + localhost).
      expect(Env.isDev, isTrue);
      expect(Env.hasBakedProductionUrl, isFalse);
    });
  });
}
