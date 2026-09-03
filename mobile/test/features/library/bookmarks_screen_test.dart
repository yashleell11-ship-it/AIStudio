import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/library/screens/bookmarks_screen.dart';
import 'package:manhwamaniacs/features/reader/models/bookmark.dart';
import 'package:manhwamaniacs/features/reader/models/chapter_manifest.dart';
import 'package:manhwamaniacs/features/reader/models/reading_progress.dart';
import 'package:manhwamaniacs/features/reader/repositories/reader_repository.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

/// Fake used only by the Bookmark Manager screen tests. All other methods
/// throw so a stray call surfaces loudly rather than passing silently with
/// empty data, matching the convention used by the other screen fakes in
/// this repository.
class _FakeReaderRepository implements ReaderRepository {
  _FakeReaderRepository({this.bookmarks = const []});

  List<Bookmark> bookmarks;
  int? deletedBookmarkId;
  Completer<void>? deleteGate;

  @override
  Future<Result<List<Bookmark>>> listBookmarks({
    String? sourceId,
    String? seriesKey,
  }) async =>
      Ok(bookmarks);

  @override
  Future<Result<void>> deleteBookmark(int bookmarkId) async {
    deletedBookmarkId = bookmarkId;
    if (deleteGate != null) await deleteGate!.future;
    bookmarks = bookmarks.where((b) => b.id != bookmarkId).toList();
    return const Ok(null);
  }

  @override
  Future<Result<Bookmark>> addBookmark({
    required String sourceId,
    required String seriesKey,
    required String chapterKey,
    required int page,
    String? note,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<ChapterManifest>> manifest({
    required String sourceId,
    required String seriesKey,
    required String chapterKey,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<ReadingProgress>> saveProgress(ProgressPush push) =>
      throw UnimplementedError();

  @override
  Future<Result<({int saved, int advanced})>> saveProgressBatch(
    List<ProgressPush> pushes,
  ) =>
      throw UnimplementedError();

  @override
  Future<Result<List<ReadingProgress>>> seriesProgress({
    required String sourceId,
    required String seriesKey,
  }) =>
      throw UnimplementedError();
}

Bookmark _bookmark({int id = 1, int page = 3}) => Bookmark(
      id: id,
      sourceId: 'asurascans',
      seriesKey: 'solo-leveling',
      chapterKey: '132',
      page: page,
      note: 'Great scene',
      createdAt: DateTime(2026),
    );

Future<void> _pumpScreen(
  WidgetTester tester, {
  required _FakeReaderRepository repo,
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
    ],
  );

  await tester.pumpWidget(
    ProviderScope(
      overrides: [readerRepositoryProvider.overrideWithValue(repo)],
      child: MaterialApp.router(routerConfig: router),
    ),
  );
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 100));
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('BookmarksScreen', () {
    testWidgets('shows an empty state when there are no bookmarks', (tester) async {
      await _pumpScreen(tester, repo: _FakeReaderRepository());

      expect(find.text('No bookmarks yet'), findsOneWidget);
    });

    testWidgets('renders bookmark cards with source, chapter, and page', (tester) async {
      await _pumpScreen(
        tester,
        repo: _FakeReaderRepository(bookmarks: [_bookmark()]),
      );

      // No chapter number is known for a bookmark, so the chapter label falls
      // back to the opaque chapter key itself.
      expect(find.text('132'), findsOneWidget);
      expect(find.text('asurascans'), findsOneWidget);
      expect(find.text('Page 3'), findsOneWidget);
      expect(find.text('Great scene'), findsOneWidget);
    });

    testWidgets('tapping a bookmark navigates to the reader at that page', (tester) async {
      String? navigated;
      await _pumpScreen(
        tester,
        repo: _FakeReaderRepository(bookmarks: [_bookmark()]),
        onNavigate: (location) => navigated = location,
      );

      await tester.tap(find.text('132'));
      await tester.pumpAndSettle();

      expect(navigated, isNotNull);
      expect(navigated, contains('/library/read/asurascans/solo-leveling/132'));
      expect(navigated, contains('page=3'));
      expect(find.text('READER'), findsOneWidget);
    });

    testWidgets('removing a bookmark calls deleteBookmark and updates the list',
        (tester) async {
      final repo = _FakeReaderRepository(bookmarks: [_bookmark()]);
      await _pumpScreen(tester, repo: repo);

      expect(find.text('132'), findsOneWidget);

      await tester.tap(find.byIcon(Icons.delete_outline));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(repo.deletedBookmarkId, 1);
      expect(find.text('No bookmarks yet'), findsOneWidget);
    });

    testWidgets('disables the delete button while a removal is pending', (tester) async {
      final repo = _FakeReaderRepository(bookmarks: [_bookmark()])
        ..deleteGate = Completer<void>();
      await _pumpScreen(tester, repo: repo);

      await tester.tap(find.byIcon(Icons.delete_outline));
      await tester.pump();

      final button = tester.widget<IconButton>(
        find.ancestor(
          of: find.byIcon(Icons.delete_outline),
          matching: find.byType(IconButton),
        ),
      );
      expect(button.onPressed, isNull);

      repo.deleteGate!.complete();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('No bookmarks yet'), findsOneWidget);
    });
  });
}
