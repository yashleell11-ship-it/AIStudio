import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/reader/models/reader_chapter.dart';
import 'package:manhwamaniacs/features/reader/models/reader_page.dart';
import 'package:manhwamaniacs/features/reader/widgets/reader_content.dart';
import 'package:manhwamaniacs/features/reader/widgets/reader_edge_back_gesture.dart';
import 'package:manhwamaniacs/features/settings/models/reader_defaults.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _readingDirectionKey = 'settings_reading_direction';

/// iPhone-sized, so the screen-width fractions in the thresholds are realistic.
const _phone = Size(430, 932);

ReaderChapter _chapter() => ReaderChapter(
      id: '1',
      seriesId: '1',
      title: 'Chapter 1',
      pageCount: 3,
      mode: ReaderMode.local,
      pages: List.generate(
        3,
        (index) => ReaderPage(
          id: '${101 + index}',
          number: index + 1,
          imageUrl: 'http://example.test/reader/page/${101 + index}/image',
          width: 800,
          height: 1200,
        ),
      ),
    );

/// Mounts the strip on its own inside a Stack, the way `ReaderContent` does.
Widget _harness({required bool enabled, required VoidCallback onBack}) {
  return Directionality(
    textDirection: TextDirection.ltr,
    child: MediaQuery(
      data: const MediaQueryData(size: _phone),
      child: Stack(
        children: [
          const Positioned.fill(child: ColoredBox(color: Color(0xFF000000))),
          ReaderEdgeBackGesture(enabled: enabled, onBack: onBack),
        ],
      ),
    ),
  );
}

Future<Widget> _reader({
  required ReadingDirection direction,
  required TargetPlatform platform,
}) async {
  SharedPreferences.setMockInitialValues({
    _readingDirectionKey: direction.name,
  });
  final prefs = await SharedPreferences.getInstance();
  return ProviderScope(
    overrides: [sharedPrefsProvider.overrideWithValue(prefs)],
    child: MaterialApp(
      theme: ThemeData(platform: platform),
      home: ReaderContent(
        chapter: _chapter(),
        scrollStorageKey: '1',
        onBack: () {},
        onOpenSeries: () {},
      ),
    ),
  );
}

/// Pumps the reader and reports whether the edge strip is live.
Future<bool> _gestureEnabled(
  WidgetTester tester, {
  required ReadingDirection direction,
  required TargetPlatform platform,
}) async {
  await tester.binding.setSurfaceSize(_phone);
  addTearDown(() => tester.binding.setSurfaceSize(null));

  await tester.pumpWidget(await _reader(direction: direction, platform: platform));
  await tester.pump();

  return tester
      .widget<ReaderEdgeBackGesture>(find.byType(ReaderEdgeBackGesture))
      .enabled;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('ReaderEdgeBackGesture', () {
    testWidgets('a fling from the leading edge leaves the chapter',
        (tester) async {
      var backs = 0;
      await tester.pumpWidget(_harness(enabled: true, onBack: () => backs++));

      // Start inside the 20pt strip and flick right — how an iOS back-swipe is
      // actually performed.
      await tester.flingFrom(const Offset(8, 400), const Offset(220, 0), 1200);
      await tester.pumpAndSettle();

      expect(backs, 1);
    });

    testWidgets('a short, slow drag does not', (tester) async {
      var backs = 0;
      await tester.pumpWidget(_harness(enabled: true, onBack: () => backs++));

      // ~40pt over 320ms: under the half-screen distance rule and well under
      // one screen width per second. This gesture has no visual tracking to
      // warn you it is about to fire, so it has to be hard to trigger by
      // accident.
      final gesture = await tester.startGesture(const Offset(8, 400));
      for (var i = 0; i < 20; i++) {
        await gesture.moveBy(const Offset(2, 0));
        await tester.pump(const Duration(milliseconds: 16));
      }
      await gesture.up();
      await tester.pumpAndSettle();

      expect(backs, 0);
    });

    testWidgets('a fling that starts outside the strip does not',
        (tester) async {
      var backs = 0;
      await tester.pumpWidget(_harness(enabled: true, onBack: () => backs++));

      await tester.flingFrom(const Offset(200, 400), const Offset(220, 0), 1200);
      await tester.pumpAndSettle();

      expect(backs, 0);
    });

    testWidgets('renders no hit-testable strip when disabled', (tester) async {
      var backs = 0;
      await tester.pumpWidget(_harness(enabled: false, onBack: () => backs++));

      await tester.flingFrom(const Offset(8, 400), const Offset(220, 0), 1200);
      await tester.pumpAndSettle();

      expect(backs, 0);
      expect(find.byType(GestureDetector), findsNothing);
    });
  });

  group('ReaderContent gates the gesture', () {
    testWidgets('iOS + vertical mode: enabled', (tester) async {
      expect(
        await _gestureEnabled(
          tester,
          direction: ReadingDirection.vertical,
          platform: TargetPlatform.iOS,
        ),
        isTrue,
      );
    });

    testWidgets('iOS + horizontal mode: disabled — the page list owns that axis',
        (tester) async {
      // The whole point of the gate. A horizontal reader whose left edge eats
      // page-turn drags is worse than one with no back gesture at all.
      expect(
        await _gestureEnabled(
          tester,
          direction: ReadingDirection.leftToRight,
          platform: TargetPlatform.iOS,
        ),
        isFalse,
      );
    });

    testWidgets('Android: disabled — the system back gesture already covers it',
        (tester) async {
      expect(
        await _gestureEnabled(
          tester,
          direction: ReadingDirection.vertical,
          platform: TargetPlatform.android,
        ),
        isFalse,
      );
    });
  });
}
