import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/reader/models/chapter_manifest.dart';
import 'package:manhwamaniacs/features/reader/models/reader_chapter.dart';
import 'package:manhwamaniacs/features/reader/providers/reader_chapter_provider.dart';
import 'package:manhwamaniacs/features/reader/repositories/reader_repository.dart';
import 'package:manhwamaniacs/features/sources/providers/source_reader_provider.dart';
import 'package:manhwamaniacs/features/sources/repositories/sources_repository.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';
import 'package:mocktail/mocktail.dart';

import '../../support/downloads_test_support.dart';

/// **The acceptance test that matters** (spec §3): airplane mode, cold
/// start, server unreachable — a chapter downloaded in an earlier session
/// still reads end to end, with zero network involved.
///
/// "Cold start" is modeled faithfully: nothing here reuses a warm manifest
/// cache or a live server round trip from a previous test — the on-device
/// store is the *only* thing populated before the reader ever asks for this
/// chapter, exactly like a phone relaunched with the server unreachable.
/// "Airplane mode" is modeled as a [Dio]-backed [ReaderRepository] /
/// [SourcesRepository] whose every call fails with a [NetworkError] — the
/// same shape a real Dio call throws when there is no connection.
class _FailingReaderRepository extends Mock implements ReaderRepository {}

class _FailingSourcesRepository extends Mock implements SourcesRepository {}

const _networkDown = NetworkError(message: 'No route to host', host: 'app.manhwamaniacs.xyz');

const _id = (sourceId: 'asura', seriesKey: 'solo-leveling', chapterKey: '1');

void main() {
  initSqfliteFfiForTests();

  late TestDownloadsHarness harness;

  setUp(() async {
    harness = await TestDownloadsHarness.create();
  });

  tearDown(() async {
    await harness.dispose();
  });

  /// Fully downloads [_id] into the store — the "earlier session, on
  /// Wi-Fi" half of the scenario — before the "now, offline" half begins.
  Future<void> downloadChapterInAnEarlierSession() async {
    final store = harness.storeFor('u1p1');
    final rowId = await store.ensureQueued(
      id: _id,
      chapterNumber: 1,
      title: 'The Weakest Hunter',
      seriesTitle: 'Solo Leveling',
    );
    await store.updateManifestInfo(rowId: rowId, pageCount: 3, chapterNumber: 1);
    for (var page = 1; page <= 3; page++) {
      await store.savePage(rowId: rowId, pageNumber: page, bytes: [page, page, page]);
    }
    final completed = await store.markCompleteIfAllPagesPresent(rowId);
    expect(completed, isTrue, reason: 'test setup: the chapter must actually be complete');
  }

  group('the library (followed-series) reader', () {
    test(
      'airplane mode + cold start + server unreachable -> a downloaded '
      'chapter renders end to end',
      () async {
        await downloadChapterInAnEarlierSession();

        final failingRepo = _FailingReaderRepository();
        when(
          () => failingRepo.manifest(
            sourceId: any(named: 'sourceId'),
            seriesKey: any(named: 'seriesKey'),
            chapterKey: any(named: 'chapterKey'),
          ),
        ).thenAnswer((_) async => const Err(_networkDown));

        final container = ProviderContainer(
          overrides: [
            readerRepositoryProvider.overrideWithValue(failingRepo),
            downloadsStoreProvider.overrideWithValue(harness.storeFor('u1p1')),
          ],
        );
        addTearDown(container.dispose);

        final resolved = await container.read(resolvedReaderChapterProvider(_id).future);

        // The reader rendered — not an error screen — entirely from disk.
        expect(resolved.isOffline, isTrue);
        expect(resolved.chapter.pages, hasLength(3));
        expect(resolved.chapter.title, contains('1'));
        expect(resolved.chapter.seriesTitle, 'Solo Leveling');

        // Every page is a real file with the exact bytes downloaded earlier
        // — not a network URL the (unreachable) server would have to serve.
        for (var i = 0; i < 3; i++) {
          final page = resolved.chapter.pages[i];
          expect(page.imageUrl, isEmpty);
          expect(page.localFile, isNotNull);
          expect(page.localFile!.existsSync(), isTrue);
          final pageNumber = i + 1;
          expect(page.localFile!.readAsBytesSync(), [pageNumber, pageNumber, pageNumber]);
        }

        // No manifest to fall back on offline — prev/next are honestly
        // absent rather than guessed at.
        expect(resolved.prev, isNull);
        expect(resolved.next, isNull);

        // The repository really was asked, and really did fail — this is
        // the fallback path, not a lucky online success.
        verify(
          () => failingRepo.manifest(
            sourceId: _id.sourceId,
            seriesKey: _id.seriesKey,
            chapterKey: _id.chapterKey,
          ),
        ).called(1);
      },
    );

    test(
      'offline with the chapter NOT downloaded surfaces the real network '
      'error, not a fabricated one',
      () async {
        final failingRepo = _FailingReaderRepository();
        when(
          () => failingRepo.manifest(
            sourceId: any(named: 'sourceId'),
            seriesKey: any(named: 'seriesKey'),
            chapterKey: any(named: 'chapterKey'),
          ),
        ).thenAnswer((_) async => const Err(_networkDown));

        final container = ProviderContainer(
          overrides: [
            readerRepositoryProvider.overrideWithValue(failingRepo),
            downloadsStoreProvider.overrideWithValue(harness.storeFor('u1p1')),
          ],
        );
        addTearDown(container.dispose);

        await expectLater(
          container.read(resolvedReaderChapterProvider(_id).future),
          throwsA(same(_networkDown)),
        );
      },
    );

    test('online success overlays on-device pages onto the fetched manifest',
        () async {
      // Only pages 1 and 2 were downloaded (e.g. the queue paused) — page 3
      // must still come from the network, not be treated as missing.
      final store = harness.storeFor('u1p1');
      final rowId = await store.ensureQueued(id: _id);
      await store.updateManifestInfo(rowId: rowId, pageCount: 3);
      await store.savePage(rowId: rowId, pageNumber: 1, bytes: [1]);
      await store.savePage(rowId: rowId, pageNumber: 2, bytes: [2]);

      final onlineRepo = _FailingReaderRepository();
      when(
        () => onlineRepo.manifest(
          sourceId: any(named: 'sourceId'),
          seriesKey: any(named: 'seriesKey'),
          chapterKey: any(named: 'chapterKey'),
        ),
      ).thenAnswer(
        (_) async => Ok(
          ChapterManifest(
            sourceId: _id.sourceId,
            seriesKey: _id.seriesKey,
            chapterKey: _id.chapterKey,
            chapterNumber: 1,
            pageCount: 3,
            prev: null,
            next: '2',
            pages: const [
              ManifestPage(number: 1, url: '/sources/asura/pages/1/image'),
              ManifestPage(number: 2, url: '/sources/asura/pages/2/image'),
              ManifestPage(number: 3, url: '/sources/asura/pages/3/image'),
            ],
          ),
        ),
      );

      final container = ProviderContainer(
        overrides: [
          readerRepositoryProvider.overrideWithValue(onlineRepo),
          downloadsStoreProvider.overrideWithValue(harness.storeFor('u1p1')),
        ],
      );
      addTearDown(container.dispose);

      final resolved = await container.read(resolvedReaderChapterProvider(_id).future);

      expect(resolved.isOffline, isFalse);
      expect(resolved.next, '2'); // manifest data survives the overlay
      expect(resolved.chapter.pages[0].localFile, isNotNull); // from disk
      expect(resolved.chapter.pages[1].localFile, isNotNull); // from disk
      expect(resolved.chapter.pages[2].localFile, isNull); // from network
      expect(resolved.chapter.pages[2].imageUrl, isNotEmpty);
    });
  });

  group('the online source-browse reader', () {
    test(
      'airplane mode + cold start + server unreachable -> the same '
      'downloaded chapter renders end to end from the *other* reader entry '
      'point',
      () async {
        await downloadChapterInAnEarlierSession();

        final failingRepo = _FailingSourcesRepository();
        when(
          () => failingRepo.getReaderChapter(any(), any(), any()),
        ).thenAnswer((_) async => const Err<ReaderChapter>(_networkDown));

        final container = ProviderContainer(
          overrides: [
            sourcesRepositoryProvider.overrideWithValue(failingRepo),
            downloadsStoreProvider.overrideWithValue(harness.storeFor('u1p1')),
          ],
        );
        addTearDown(container.dispose);

        final chapter = await container.read(
          sourceReaderChapterProvider(
            (sourceId: _id.sourceId, seriesId: _id.seriesKey, chapterId: _id.chapterKey),
          ).future,
        );

        expect(chapter.pages, hasLength(3));
        expect(chapter.pages.every((p) => p.localFile != null), isTrue);
        expect(chapter.pages.every((p) => p.localFile!.existsSync()), isTrue);
      },
    );
  });
}
