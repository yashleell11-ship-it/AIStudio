import 'package:aistudio_mobile/features/library/utils/recent_searches.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('recent_searches', () {
    test('stores deduplicated recent searches', () async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();

      await writeRecentSearch(prefs, 'Solo Leveling');
      await writeRecentSearch(prefs, 'fantasy');
      await writeRecentSearch(prefs, 'solo leveling');

      expect(readRecentSearches(prefs), ['solo leveling', 'fantasy']);
    });

    test('ignores terms shorter than two characters', () async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();

      await writeRecentSearch(prefs, 'a');
      expect(readRecentSearches(prefs), isEmpty);
    });
  });
}
