import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/settings/models/app_changelog.dart';
import 'package:manhwamaniacs/features/settings/providers/app_changelog_provider.dart';
import 'package:manhwamaniacs/features/settings/widgets/whats_new_sheet.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('ChangelogRelease.fromJson', () {
    test('parses a well-formed entry', () {
      final release = ChangelogRelease.fromJson({
        'version': '1.2.0',
        'build': 3,
        'date': 'July 2026',
        'highlights': ['Sepia and grayscale', 'High refresh'],
      });

      expect(release.version, '1.2.0');
      expect(release.build, 3);
      expect(release.date, 'July 2026');
      expect(release.highlights, ['Sepia and grayscale', 'High refresh']);
    });

    test('is resilient to missing and malformed fields', () {
      final release = ChangelogRelease.fromJson({
        'version': null,
        'build': null,
        'highlights': 'not a list',
      });

      expect(release.version, '');
      expect(release.build, 0);
      expect(release.date, '');
      expect(release.highlights, isEmpty);
    });

    test('drops non-string highlights', () {
      final release = ChangelogRelease.fromJson({
        'version': '1.0.0',
        'build': 1,
        'highlights': ['Real note', 42, null],
      });

      expect(release.highlights, ['Real note']);
    });
  });

  Widget wrap(List<ChangelogRelease> releases) {
    return ProviderScope(
      overrides: [
        appChangelogProvider.overrideWith((ref) async => releases),
      ],
      child: const MaterialApp(home: Scaffold(body: WhatsNewSheet())),
    );
  }

  testWidgets('renders release notes with a Latest badge on the newest',
      (tester) async {
    await tester.pumpWidget(wrap(const [
      ChangelogRelease(
        version: '1.2.0',
        build: 3,
        date: 'July 2026',
        highlights: ['Sepia and grayscale reader modes'],
      ),
      ChangelogRelease(
        version: '1.1.0',
        build: 2,
        date: 'July 2026',
        highlights: ['In-app update system'],
      ),
    ]),);
    await tester.pumpAndSettle();

    expect(find.text("What's new"), findsOneWidget);
    expect(find.text('v1.2.0'), findsOneWidget);
    expect(find.text('v1.1.0'), findsOneWidget);
    expect(find.text('Latest'), findsOneWidget);
    expect(find.text('Sepia and grayscale reader modes'), findsOneWidget);
    expect(find.text('In-app update system'), findsOneWidget);
  });

  testWidgets('shows a graceful message when no notes are available',
      (tester) async {
    await tester.pumpWidget(wrap(const []));
    await tester.pumpAndSettle();

    expect(find.text('Release notes unavailable'), findsOneWidget);
  });
}
