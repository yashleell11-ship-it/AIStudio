import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/settings/utils/settings_search_index.dart';

void main() {
  group('filterSettingsSearchIndex', () {
    test('returns the full index for an empty query', () {
      expect(filterSettingsSearchIndex(''), settingsSearchIndex);
      expect(filterSettingsSearchIndex('   '), settingsSearchIndex);
    });

    test('matches on label, case-insensitively', () {
      final results = filterSettingsSearchIndex('THEME');
      expect(results.map((e) => e.label), contains('Theme'));
    });

    test('matches on subtitle too', () {
      final results = filterSettingsSearchIndex('FPS');
      expect(results.map((e) => e.label), contains('Refresh rate'));
    });

    test('returns nothing for a query that matches no setting', () {
      expect(filterSettingsSearchIndex('xyz-not-a-setting'), isEmpty);
    });

    test('the volume key navigation setting is discoverable', () {
      final results = filterSettingsSearchIndex('volume');
      expect(results.map((e) => e.label), contains('Volume key navigation'));
    });
  });
}
