import 'package:aistudio_mobile/features/reader/utils/scroll_storage.dart';
import 'package:flutter_test/flutter_test.dart';
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
  });
}
