import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/library/providers/bookmarks_provider.dart';
import 'package:manhwamaniacs/features/library/screens/bookmarks_screen.dart';
import 'package:manhwamaniacs/features/reader/models/bookmark.dart';

import '../../support/test_overrides.dart';

/// The screen is driven through a fake [BookmarksNotifier] rather than the
/// real FFI-backed store, and deliberately so — see the note in
/// `downloads_storage_card_test.dart`: sqflite_common_ffi's background
/// isolate needs real event-loop turns that `testWidgets`' FakeAsync zone
/// does not supply, and routing around that with `runAsync` opens a second
/// SQLite connection which deadlocks against the widget's own.
///
/// So this file tests what a screen test should — what the card renders and
/// where a tap goes — while the device-first read, the tombstone and the
/// outbox are covered against a real store in `bookmarks_provider_test.dart`
/// and `bookmarks_store_test.dart`.
class _FakeBookmarksNotifier extends BookmarksNotifier {
  _FakeBookmarksNotifier(this._bookmarks, {this.deleteGate});

  List<Bookmark> _bookmarks;
  final Completer<void>? deleteGate;
  Bookmark? deleted;

  @override
  Future<BookmarksState> build() async => BookmarksState(bookmarks: _bookmarks);

  @override
  Future<void> refresh() async {}

  @override
  Future<AppError?> deleteBookmark(Bookmark bookmark) async {
    deleted = bookmark;
    state = AsyncData(
      BookmarksState(bookmarks: _bookmarks, actionPending: true),
    );
    if (deleteGate != null) await deleteGate!.future;
    _bookmarks =
        _bookmarks.where((b) => b.clientId != bookmark.clientId).toList();
    state = AsyncData(BookmarksState(bookmarks: _bookmarks));
    return null;
  }
}

Bookmark _manga({
  String clientId = 'c1',
  int index = 7,
  double fraction = 0.62,
  int total = 11,
}) =>
    Bookmark(
      clientId: clientId,
      sourceId: 'asurascans',
      seriesKey: 'solo-leveling',
      chapterKey: '132',
      seriesTitle: 'Solo Leveling',
      chapterNumber: 14,
      anchorIndex: index,
      anchorFraction: fraction,
      anchorTotal: total,
      note: 'Great scene',
      createdAt: DateTime.utc(2026, 9, 5),
      updatedAt: DateTime.utc(2026, 9, 5),
    );

Bookmark _novel() => Bookmark(
      clientId: 'n1',
      sourceId: 'novelbuddy',
      seriesKey: 'tbate',
      chapterKey: 'c14',
      seriesTitle: 'The Beginning After The End',
      chapterNumber: 14,
      mediaType: BookmarkMedia.novel,
      anchorIndex: 340,
      anchorFraction: 0.5,
      anchorTotal: 800,
      snippet: '…the mana core pulsed once, and the room went very quiet.',
      createdAt: DateTime.utc(2026, 9, 5),
      updatedAt: DateTime.utc(2026, 9, 5),
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  Future<void> pumpScreen(
    WidgetTester tester, {
    required _FakeBookmarksNotifier notifier,
    void Function(String)? onNavigate,
  }) async {
    final router = GoRouter(
      initialLocation: Routes.bookmarks,
      routes: [
        GoRoute(
          path: Routes.bookmarks,
          builder: (_, __) => const BookmarksScreen(),
        ),
        GoRoute(
          path: Routes.reader,
          builder: (_, state) {
            onNavigate?.call(state.uri.toString());
            return const Scaffold(body: Center(child: Text('READER')));
          },
        ),
        GoRoute(
          path: Routes.novelReader,
          builder: (_, state) {
            onNavigate?.call(state.uri.toString());
            return const Scaffold(body: Center(child: Text('NOVEL READER')));
          },
        ),
      ],
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          bookmarksProvider.overrideWith(() => notifier),
          // The screen asks which mode it is listing; pinning it keeps this
          // test off SharedPreferences.
          ...contentModeOverrides(),
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
  }

  group('BookmarksScreen', () {
    testWidgets('shows an empty state when there are no bookmarks',
        (tester) async {
      await pumpScreen(tester, notifier: _FakeBookmarksNotifier(const []));

      expect(find.text('No bookmarks yet'), findsOneWidget);
    });

    testWidgets('renders a manga bookmark with its exact position',
        (tester) async {
      await pumpScreen(tester, notifier: _FakeBookmarksNotifier([_manga()]));

      expect(find.text('Solo Leveling'), findsOneWidget);
      expect(find.text('asurascans'), findsOneWidget);
      // (7 - 1 + 0.62) / 11 = 0.6018 -> 60%.
      expect(find.text('60% of chapter 14'), findsOneWidget);
      expect(find.text('Great scene'), findsOneWidget);
    });

    testWidgets('a bookmark with no unit count claims no percentage',
        (tester) async {
      // What a row migrated from the old page-only schema looks like: an
      // honest "page 4", never a fabricated "0% of the chapter".
      await pumpScreen(
        tester,
        notifier: _FakeBookmarksNotifier(
          [_manga(index: 4, fraction: 0, total: 0)],
        ),
      );

      expect(find.text('Page 4'), findsOneWidget);
      expect(find.textContaining('%'), findsNothing);
    });

    testWidgets('a novel bookmark shows the text at that point',
        (tester) async {
      await pumpScreen(tester, notifier: _FakeBookmarksNotifier([_novel()]));

      expect(find.textContaining('the mana core pulsed once'), findsOneWidget);
      // (340 - 1 + 0.5) / 800 = 0.4244 -> 42%.
      expect(find.text('42% of chapter 14'), findsOneWidget);
    });

    testWidgets('tapping a manga bookmark opens the reader at the exact spot',
        (tester) async {
      String? navigated;
      await pumpScreen(
        tester,
        notifier: _FakeBookmarksNotifier([_manga()]),
        onNavigate: (location) => navigated = location,
      );

      await tester.tap(find.text('Solo Leveling'));
      await tester.pumpAndSettle();

      expect(navigated, contains('/library/read/asurascans/solo-leveling/132'));
      expect(navigated, contains('page=7'));
      // The fraction, not just the page — a page on a webtoon strip is
      // thousands of pixels tall.
      expect(navigated, contains('at=0.6200'));
      expect(find.text('READER'), findsOneWidget);
    });

    testWidgets('tapping a novel bookmark opens it by paragraph, not by bucket',
        (tester) async {
      String? navigated;
      await pumpScreen(
        tester,
        notifier: _FakeBookmarksNotifier([_novel()]),
        onNavigate: (location) => navigated = location,
      );

      await tester.tap(find.text('The Beginning After The End'));
      await tester.pumpAndSettle();

      expect(navigated, contains('/novels/read/novelbuddy/tbate/c14'));
      expect(navigated, contains('para=340'));
      expect(navigated, contains('at=0.5000'));
      // `page=` would be read as a progress BUCKET (1-100) and would land the
      // reader at the end of the chapter.
      expect(navigated, isNot(contains('page=')));
    });

    testWidgets('removing a bookmark hands the whole row to the notifier',
        (tester) async {
      final notifier = _FakeBookmarksNotifier([_manga()]);
      await pumpScreen(tester, notifier: notifier);

      await tester.tap(find.byIcon(Icons.delete_outline));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      // The row, not a server id: a bookmark made offline has no server id
      // yet, and its client id is the only thing that identifies it.
      expect(notifier.deleted?.clientId, 'c1');
      expect(find.text('No bookmarks yet'), findsOneWidget);
    });

    testWidgets('disables the delete button while a removal is pending',
        (tester) async {
      final gate = Completer<void>();
      final notifier = _FakeBookmarksNotifier([_manga()], deleteGate: gate);
      await pumpScreen(tester, notifier: notifier);

      await tester.tap(find.byIcon(Icons.delete_outline));
      await tester.pump();

      final button = tester.widget<IconButton>(
        find.ancestor(
          of: find.byIcon(Icons.delete_outline),
          matching: find.byType(IconButton),
        ),
      );
      expect(button.onPressed, isNull);

      gate.complete();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('No bookmarks yet'), findsOneWidget);
    });
  });
}
