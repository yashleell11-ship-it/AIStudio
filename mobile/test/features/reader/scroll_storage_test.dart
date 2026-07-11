import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/reader/utils/scroll_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('scroll_storage', () {
    test('writes and reads scroll position per chapter', () async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();

      await writeReaderScrollPosition(prefs, 42, 512.4);
      expect(readReaderScrollPosition(prefs, 42), 512);

      expect(readReaderScrollPosition(prefs, 99), isNull);
    });

    group('by key', () {
      test('writes and reads scroll position for an opaque key', () async {
        SharedPreferences.setMockInitialValues({});
        final prefs = await SharedPreferences.getInstance();

        const key = 'mangadex:abc:chapter-1';
        await writeReaderScrollPositionByKey(prefs, key, 1024.7);
        expect(readReaderScrollPositionByKey(prefs, key), 1025);
      });

      test('returns null for unknown key', () async {
        SharedPreferences.setMockInitialValues({});
        final prefs = await SharedPreferences.getInstance();

        expect(readReaderScrollPositionByKey(prefs, 'missing'), isNull);
      });

      test('is isolated from int-keyed storage', () async {
        SharedPreferences.setMockInitialValues({});
        final prefs = await SharedPreferences.getInstance();

        await writeReaderScrollPosition(prefs, 42, 100);
        // The composite key '42:x' must not collide with chapter id 42.
        expect(readReaderScrollPositionByKey(prefs, '42:x'), isNull);
      });
    });
  });
}
