import 'dart:async';

import 'package:aistudio_mobile/features/reader/models/reader_chapter.dart';
import 'package:aistudio_mobile/features/reader/models/reader_page.dart';
import 'package:aistudio_mobile/features/reader/utils/reader_wakelock.dart';
import 'package:aistudio_mobile/features/reader/widgets/reader_content.dart';
import 'package:aistudio_mobile/features/settings/models/reader_defaults.dart';
import 'package:aistudio_mobile/features/settings/providers/settings_provider.dart';
import 'package:aistudio_mobile/shared/providers/core_providers.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _readingDirectionKey = 'settings_reading_direction';
const _readerFitModeKey = 'settings_reader_fit_mode';
const _keepScreenAwakeKey = 'settings_keep_screen_awake';
const _autoNextChapterKey = 'settings_auto_next_chapter';

ReaderChapter _tallChapter({String? nextChapterId}) {
  return ReaderChapter(
    id: '1',
    seriesId: '1',
    title: 'Chapter 1',
    pageCount: 6,
    mode: ReaderMode.local,
    nextChapterId: nextChapterId,
    pages: List.generate(
      6,
      (index) => ReaderPage(
        id: '${101 + index}',
        number: index + 1,
        imageUrl: 'http://example.test/reader/page/${101 + index}/image',
        width: 800,
        height: 1200,
      ),
    ),
  );
}

class _FakeReaderWakelock implements ReaderWakelock {
  var enableCalls = 0;
  var disableCalls = 0;

  @override
  Future<void> enable() async {
    enableCalls++;
  }

  @override
  Future<void> disable() async {
    disableCalls++;
  }
}

Future<SharedPreferences> _freshPrefs([Map<String, Object> values = const {}]) async {
  SharedPreferences.setMockInitialValues(values);
  return SharedPreferences.getInstance();
}

Widget _wrap(
  SharedPreferences prefs,
  Widget child, {
  ReaderWakelock? wakelock,
}) {
  return ProviderScope(
    overrides: [
      sharedPrefsProvider.overrideWithValue(prefs),
      if (wakelock != null) readerWakelockProvider.overrideWithValue(wakelock),
    ],
    child: MaterialApp(home: child),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('Reader settings integration', () {
    testWidgets('uses vertical scroll for vertical reading direction', (tester) async {
      final prefs = await _freshPrefs({
        _readingDirectionKey: 'vertical',
      });
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        _wrap(
          prefs,
          ReaderContent(
            chapter: _tallChapter(),
            scrollStorageKey: '1',
            onBack: () {},
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      final listView = tester.widget<ListView>(find.byType(ListView));
      expect(listView.scrollDirection, Axis.vertical);
      expect(listView.reverse, isFalse);
    });

    testWidgets('uses horizontal scroll for left-to-right reading direction',
        (tester) async {
      final prefs = await _freshPrefs({
        _readingDirectionKey: 'leftToRight',
      });
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        _wrap(
          prefs,
          ReaderContent(
            chapter: _tallChapter(),
            scrollStorageKey: '1',
            onBack: () {},
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      final listView = tester.widget<ListView>(find.byType(ListView));
      expect(listView.scrollDirection, Axis.horizontal);
      expect(listView.reverse, isFalse);
    });

    testWidgets('uses reversed horizontal scroll for right-to-left direction',
        (tester) async {
      final prefs = await _freshPrefs({
        _readingDirectionKey: 'rightToLeft',
      });
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        _wrap(
          prefs,
          ReaderContent(
            chapter: _tallChapter(),
            scrollStorageKey: '1',
            onBack: () {},
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      final listView = tester.widget<ListView>(find.byType(ListView));
      expect(listView.scrollDirection, Axis.horizontal);
      expect(listView.reverse, isTrue);
    });

    testWidgets('applies fit mode from readerDefaultsProvider immediately',
        (tester) async {
      final prefs = await _freshPrefs({
        _readerFitModeKey: 'height',
      });
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        _wrap(
          prefs,
          ReaderContent(
            chapter: _tallChapter(),
            scrollStorageKey: '1',
            onBack: () {},
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      final cachedImage =
          tester.widget<CachedNetworkImage>(find.byType(CachedNetworkImage).first);
      expect(cachedImage.fit, BoxFit.fitHeight);
    });

    testWidgets('enables wakelock while reader is open when keepScreenAwake is true',
        (tester) async {
      final prefs = await _freshPrefs({
        _keepScreenAwakeKey: true,
      });
      final wakelock = _FakeReaderWakelock();
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        _wrap(
          prefs,
          ReaderContent(
            chapter: _tallChapter(),
            scrollStorageKey: '1',
            onBack: () {},
          ),
          wakelock: wakelock,
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(wakelock.enableCalls, 1);
      expect(wakelock.disableCalls, 0);
    });

    testWidgets('does not enable wakelock when keepScreenAwake is false',
        (tester) async {
      final prefs = await _freshPrefs();
      final wakelock = _FakeReaderWakelock();
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        _wrap(
          prefs,
          ReaderContent(
            chapter: _tallChapter(),
            scrollStorageKey: '1',
            onBack: () {},
          ),
          wakelock: wakelock,
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(wakelock.enableCalls, 0);
      expect(wakelock.disableCalls, 0);
    });

    testWidgets('releases wakelock on dispose', (tester) async {
      final prefs = await _freshPrefs({
        _keepScreenAwakeKey: true,
      });
      final wakelock = _FakeReaderWakelock();
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        _wrap(
          prefs,
          ReaderContent(
            chapter: _tallChapter(),
            scrollStorageKey: '1',
            onBack: () {},
          ),
          wakelock: wakelock,
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump();

      expect(wakelock.enableCalls, 1);
      expect(wakelock.disableCalls, 1);
    });

    testWidgets('auto-next fires when autoNextChapter is enabled', (tester) async {
      final prefs = await _freshPrefs({
        _autoNextChapterKey: true,
      });
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      var nextCalls = 0;
      await tester.pumpWidget(
        _wrap(
          prefs,
          ReaderContent(
            chapter: _tallChapter(nextChapterId: '2'),
            scrollStorageKey: '1',
            onBack: () {},
            onNextChapter: () => nextCalls++,
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      final controller =
          tester.widget<ListView>(find.byType(ListView)).controller!;
      controller.jumpTo(controller.position.maxScrollExtent);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 1000));

      expect(nextCalls, 1);
    });

    testWidgets('auto-next does not fire when autoNextChapter is disabled',
        (tester) async {
      final prefs = await _freshPrefs({
        _autoNextChapterKey: false,
      });
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      var nextCalls = 0;
      await tester.pumpWidget(
        _wrap(
          prefs,
          ReaderContent(
            chapter: _tallChapter(nextChapterId: '2'),
            scrollStorageKey: '1',
            onBack: () {},
            onNextChapter: () => nextCalls++,
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      final controller =
          tester.widget<ListView>(find.byType(ListView)).controller!;
      controller.jumpTo(controller.position.maxScrollExtent);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 1200));

      expect(nextCalls, 0);
    });

    test('readerDefaultsProvider reflects persisted reader preferences', () async {
      SharedPreferences.setMockInitialValues({
        _readingDirectionKey: 'rightToLeft',
        _readerFitModeKey: 'screen',
        _keepScreenAwakeKey: true,
        _autoNextChapterKey: false,
      });
      final prefs = await SharedPreferences.getInstance();
      final container = ProviderContainer(
        overrides: [sharedPrefsProvider.overrideWithValue(prefs)],
      );
      addTearDown(container.dispose);

      final defaults = container.read(readerDefaultsProvider);
      expect(defaults.direction, ReadingDirection.rightToLeft);
      expect(defaults.fitMode, ReaderFitMode.screen);
      expect(defaults.keepScreenAwake, isTrue);
      expect(defaults.autoNextChapter, isFalse);
    });

    testWidgets('reader rebuilds when fit mode changes via provider', (tester) async {
      final prefs = await _freshPrefs({
        _readerFitModeKey: 'width',
      });
      late ProviderContainer container;
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        ProviderScope(
          overrides: [sharedPrefsProvider.overrideWithValue(prefs)],
          child: Builder(
            builder: (context) {
              container = ProviderScope.containerOf(context);
              return MaterialApp(
                home: ReaderContent(
                  chapter: _tallChapter(),
                  scrollStorageKey: '1',
                  onBack: () {},
                ),
              );
            },
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      var cachedImage =
          tester.widget<CachedNetworkImage>(find.byType(CachedNetworkImage).first);
      expect(cachedImage.fit, BoxFit.fitWidth);

      await container.read(readerDefaultsProvider.notifier).setFitMode(ReaderFitMode.height);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      cachedImage =
          tester.widget<CachedNetworkImage>(find.byType(CachedNetworkImage).first);
      expect(cachedImage.fit, BoxFit.fitHeight);
    });
  });
}
