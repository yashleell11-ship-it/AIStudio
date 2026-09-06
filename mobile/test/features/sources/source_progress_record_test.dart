import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/sources/models/source_chapter_progress.dart';
import 'package:manhwamaniacs/features/sources/providers/source_progress_provider.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/test_overrides.dart';

/// `SourceProgressNotifier.record` is the source reader's only write, and the
/// series page resumes from what it stores. It has to obey the same rule the
/// server's `merge_progress` does — a chapter's position only ever moves
/// FORWARD, and finishing is sticky — or scrolling back up inside a chapter
/// (or a stray save for a page the feed already left) rewinds "Continue".
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late ProviderContainer container;

  setUp(() async {
    SharedPreferences.setMockInitialValues(testPrefsDefaults());
    final prefs = await SharedPreferences.getInstance();
    container = ProviderContainer(
      overrides: [
        sharedPrefsProvider.overrideWithValue(prefs),
        activeProfileOverride(),
      ],
    );
    addTearDown(container.dispose);
  });

  SourceProgressNotifier notifier() =>
      container.read(sourceProgressProvider.notifier);

  Future<void> record(int page, {int pageCount = 20, String chapter = 'c5'}) =>
      notifier().record(
        sourceId: 'asura',
        seriesId: 'solo-leveling',
        chapterId: chapter,
        page: page,
        pageCount: pageCount,
      );

  SourceChapterProgress stored(String chapter) => notifier().progressFor(
        sourceId: 'asura',
        seriesId: 'solo-leveling',
        chapterId: chapter,
      )!;

  test('a forward page advances the chapter', () async {
    await record(3);
    await record(9);
    expect(stored('c5').page, 9);
  });

  test('a page behind the stored one never rewinds the chapter', () async {
    await record(18);
    await record(3);
    expect(stored('c5').page, 18);
  });

  test('finishing a chapter is sticky', () async {
    await record(20);
    expect(stored('c5').completed, isTrue);
    await record(2);
    expect(stored('c5').completed, isTrue);
    expect(stored('c5').page, 20);
  });

  test('the page count never shrinks to a partial answer', () async {
    await record(5);
    await record(6, pageCount: 0);
    expect(stored('c5').pageCount, 20);
  });
}
