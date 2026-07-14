import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/library/utils/recent_searches.dart';
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

    test('scopes history per profile id', () async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();

      await writeRecentSearch(prefs, 'profile-a-term', profileId: 1);

      // Profile B (id 2) must not see profile A's search history.
      expect(readRecentSearches(prefs, profileId: 2), isEmpty);
      expect(readRecentSearches(prefs, profileId: 1), ['profile-a-term']);

      await writeRecentSearch(prefs, 'profile-b-term', profileId: 2);
      expect(readRecentSearches(prefs, profileId: 1), ['profile-a-term']);
      expect(readRecentSearches(prefs, profileId: 2), ['profile-b-term']);
    });
  });
}
