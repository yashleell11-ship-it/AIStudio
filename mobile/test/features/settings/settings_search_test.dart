import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/settings/utils/settings_search_index.dart';

/// The index as Android renders it — the platform that shows every entry.
List<SettingsSearchEntry> _android(String query) =>
    filterSettingsSearchIndex(query, platform: TargetPlatform.android);

void main() {
  group('filterSettingsSearchIndex', () {
    test('returns the full index for an empty query', () {
      expect(_android(''), settingsSearchIndex);
      expect(_android('   '), settingsSearchIndex);
    });

    test('matches on label, case-insensitively', () {
      final results = _android('THEME');
      expect(results.map((e) => e.label), contains('Theme'));
    });

    test('matches on subtitle too', () {
      final results = _android('FPS');
      expect(results.map((e) => e.label), contains('Refresh rate'));
    });

    test('returns nothing for a query that matches no setting', () {
      expect(_android('xyz-not-a-setting'), isEmpty);
    });

    test('the volume key navigation setting is discoverable', () {
      final results = _android('volume');
      expect(results.map((e) => e.label), contains('Volume key navigation'));
    });

    // The General tab hides refresh rate and volume-key paging off Android —
    // both are backed by Android-only platform channels and silently no-op
    // elsewhere. Search must hide them too, or it offers a jump to a control
    // that is not on the screen it lands on.
    test('Android-only settings are hidden from search on iOS', () {
      final labels = filterSettingsSearchIndex('', platform: TargetPlatform.iOS)
          .map((e) => e.label);

      expect(labels, isNot(contains('Refresh rate')));
      expect(labels, isNot(contains('Volume key navigation')));
      expect(labels, contains('Reading direction'));
      expect(labels, contains('Fit mode'));
    });

    test('and stay hidden for a query that would otherwise match them', () {
      expect(
        filterSettingsSearchIndex('volume', platform: TargetPlatform.iOS),
        isEmpty,
      );
      expect(
        filterSettingsSearchIndex('refresh', platform: TargetPlatform.iOS),
        isEmpty,
      );
    });

    test('but remain on Android', () {
      final labels = _android('').map((e) => e.label);

      expect(labels, contains('Refresh rate'));
      expect(labels, contains('Volume key navigation'));
    });

    // The security controls live one push deeper than any tab, so the entry
    // has to answer to the words people type rather than to its own label
    // alone — a search for "change password" that finds nothing is a user who
    // concludes the app cannot change a password.
    test('the security page answers to what people call it', () {
      for (final query in [
        'change password',
        'sessions',
        'devices',
        'sign out everywhere',
        'security',
      ]) {
        expect(
          _android(query).map((e) => e.label),
          contains('Password & security'),
          reason: 'searching "$query" should surface the security page',
        );
      }
    });

    test('and lands on the General tab, where its card is', () {
      final entry = _android('change password').single;

      expect(entry.label, 'Password & security');
      expect(entry.tabIndex, 0);
    });
  });
}
