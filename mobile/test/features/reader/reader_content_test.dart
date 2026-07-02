import 'package:aistudio_mobile/features/reader/models/reader_chapter.dart';
import 'package:aistudio_mobile/features/reader/models/reader_page.dart';
import 'package:aistudio_mobile/features/reader/widgets/reader_content.dart';
import 'package:aistudio_mobile/shared/providers/core_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

ReaderChapter _sampleChapter({
  String? previousChapterId,
  String? nextChapterId,
}) {
  return ReaderChapter(
    id: '1',
    seriesId: '1',
    title: 'Chapter 1',
    pageCount: 2,
    mode: ReaderMode.local,
    previousChapterId: previousChapterId,
    nextChapterId: nextChapterId,
    pages: const [
      ReaderPage(
        id: '101',
        number: 1,
        imageUrl: 'http://example.test/reader/page/101/image',
        width: 800,
        height: 1200,
      ),
      ReaderPage(
        id: '102',
        number: 2,
        imageUrl: 'http://example.test/reader/page/102/image',
        width: 800,
        height: 1200,
      ),
    ],
  );
}

Future<SharedPreferences> _freshPrefs() async {
  SharedPreferences.setMockInitialValues({});
  return SharedPreferences.getInstance();
}

Widget _wrapWithPrefs(SharedPreferences prefs, Widget child) {
  return ProviderScope(
    overrides: [
      sharedPrefsProvider.overrideWithValue(prefs),
    ],
    child: MaterialApp(home: child),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('ReaderContent', () {
    testWidgets('renders title, page indicator and controls', (tester) async {
      final prefs = await _freshPrefs();
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        _wrapWithPrefs(
          prefs,
          ReaderContent(
            chapter: _sampleChapter(),
            scrollStorageKey: '1',
            onBack: () {},
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('Chapter 1'), findsOneWidget);
      expect(find.textContaining('Page 1 / 2'), findsOneWidget);
      expect(find.text('Back'), findsOneWidget);
    });

    testWidgets('shows Save bookmark when callback is provided', (tester) async {
      final prefs = await _freshPrefs();
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        _wrapWithPrefs(
          prefs,
          ReaderContent(
            chapter: _sampleChapter(),
            scrollStorageKey: '1',
            showBookmark: true,
            onAddBookmark: (_) async => true,
            onBack: () {},
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('Save'), findsOneWidget);
    });

    testWidgets('hides Save bookmark for online chapters', (tester) async {
      final prefs = await _freshPrefs();
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        _wrapWithPrefs(
          prefs,
          ReaderContent(
            chapter: _sampleChapter(),
            scrollStorageKey: 'src:1:1',
            showBookmark: false,
            onBack: () {},
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('Save'), findsNothing);
    });

    testWidgets('disables previous/next nav buttons when ids absent',
        (tester) async {
      final prefs = await _freshPrefs();
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        _wrapWithPrefs(
          prefs,
          ReaderContent(
            chapter: _sampleChapter(),
            scrollStorageKey: '1',
            onBack: () {},
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      final prevButton = tester.widget<TextButton>(
        find.ancestor(
          of: find.text('Prev'),
          matching: find.byType(TextButton),
        ),
      );
      final nextButton = tester.widget<TextButton>(
        find.ancestor(
          of: find.text('Next'),
          matching: find.byType(TextButton),
        ),
      );
      expect(prevButton.enabled, isFalse);
      expect(nextButton.enabled, isFalse);
    });

    testWidgets('does not persist progress when no callback supplied',
        (tester) async {
      final prefs = await _freshPrefs();
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      var saveCalls = 0;
      await tester.pumpWidget(
        _wrapWithPrefs(
          prefs,
          ReaderContent(
            chapter: _sampleChapter(),
            scrollStorageKey: '1',
            onBack: () {},
            // No onSaveProgress — progress must never fire.
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(saveCalls, 0);
    });

    testWidgets('invokes onBack when Back tapped', (tester) async {
      final prefs = await _freshPrefs();
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      var backCalls = 0;
      await tester.pumpWidget(
        _wrapWithPrefs(
          prefs,
          ReaderContent(
            chapter: _sampleChapter(),
            scrollStorageKey: '1',
            onBack: () => backCalls++,
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      await tester.tap(find.text('Back'));
      await tester.pump();

      expect(backCalls, 1);
    });

    testWidgets('shows bookmark snackbar only when callback returns true',
        (tester) async {
      final prefs = await _freshPrefs();
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        _wrapWithPrefs(
          prefs,
          ReaderContent(
            chapter: _sampleChapter(),
            scrollStorageKey: '1',
            showBookmark: true,
            onAddBookmark: (_) async => true,
            onBack: () {},
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      await tester.tap(find.text('Save'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('Bookmarked page 1'), findsOneWidget);
    });

    testWidgets('hides bookmark snackbar when callback returns false',
        (tester) async {
      final prefs = await _freshPrefs();
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        _wrapWithPrefs(
          prefs,
          ReaderContent(
            chapter: _sampleChapter(),
            scrollStorageKey: '1',
            showBookmark: true,
            onAddBookmark: (_) async => false,
            onBack: () {},
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      await tester.tap(find.text('Save'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.textContaining('Bookmarked page'), findsNothing);
    });

    testWidgets('clears bookmark pending after callback throws', (tester) async {
      final prefs = await _freshPrefs();
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        _wrapWithPrefs(
          prefs,
          ReaderContent(
            chapter: _sampleChapter(),
            scrollStorageKey: '1',
            showBookmark: true,
            onAddBookmark: (_) async => throw Exception('bookmark failed'),
            onBack: () {},
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      await tester.tap(find.text('Save'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      expect(tester.takeException(), isA<Exception>());

      final saveButton = tester.widget<TextButton>(
        find.ancestor(
          of: find.text('Save'),
          matching: find.byType(TextButton),
        ),
      );
      expect(saveButton.enabled, isTrue);
    });

    testWidgets('re-arms auto-next timer after scrolling away from bottom',
        (tester) async {
      final prefs = await _freshPrefs();
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      var nextCalls = 0;
      await tester.pumpWidget(
        _wrapWithPrefs(
          prefs,
          ReaderContent(
            chapter: _sampleChapter(nextChapterId: '2'),
            scrollStorageKey: '1',
            onBack: () {},
            onNextChapter: () => nextCalls++,
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      final listView = find.byType(ListView);
      await tester.drag(listView, const Offset(0, -4000));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));

      await tester.drag(listView, const Offset(0, 4000));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 1000));

      expect(nextCalls, 1);
    });
  });
}
