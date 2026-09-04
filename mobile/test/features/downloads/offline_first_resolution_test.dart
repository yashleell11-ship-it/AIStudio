import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/downloads/models/saved_chapter.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_store.dart';
import 'package:manhwamaniacs/features/novels/models/novel_chapter.dart';
import 'package:manhwamaniacs/features/novels/providers/novel_chapter_provider.dart';
import 'package:manhwamaniacs/features/novels/repositories/novels_repository.dart';
import 'package:manhwamaniacs/features/reader/models/chapter_manifest.dart';
import 'package:manhwamaniacs/features/reader/models/reader_chapter.dart';
import 'package:manhwamaniacs/features/reader/providers/reader_chapter_provider.dart';
import 'package:manhwamaniacs/features/reader/repositories/reader_repository.dart';
import 'package:manhwamaniacs/features/sources/providers/source_reader_provider.dart';
import 'package:manhwamaniacs/features/sources/repositories/sources_repository.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';
import 'package:mocktail/mocktail.dart';

import '../../support/downloads_test_support.dart';

/// **The ordering test** (spec R3). `offline_reader_acceptance_test.dart`
/// proves a downloaded chapter reads when the network is *gone*; this proves
/// the reader does not so much as *wait* on the network when the chapter is
/// already on the phone — with connectivity, with a server that would answer
/// perfectly well given time.
///
/// The network here does not fail, it **hangs**: every repository call returns
/// a future that is never completed. A reader that awaited it first would sit
/// on the skeleton forever, so "resolves at all" is the assertion, and it is
/// one no amount of reordering can accidentally still satisfy.
///
/// This is the exact behaviour a later refactor will want to "helpfully"
/// reverse back to fetch-then-fall-back, which is why it is pinned here rather
/// than left to the doc comment on the provider.
class _HangingReaderRepository extends Mock implements ReaderRepository {}

class _HangingSourcesRepository extends Mock implements SourcesRepository {}

class _HangingNovelsRepository extends Mock implements NovelsRepository {}

const _id = (sourceId: 'asura', seriesKey: 'solo-leveling', chapterKey: '1');

/// How long a hung network is given to prove it is not being awaited. Any
/// value works — the future never completes — so this is only the budget for
/// "the disk answer really did arrive without it".
const _patience = Duration(seconds: 2);

void main() {
  initSqfliteFfiForTests();

  late TestDownloadsHarness harness;

  setUp(() async {
    harness = await TestDownloadsHarness.create();
  });

  tearDown(() async {
    await harness.dispose();
  });

  /// A manga chapter, fully downloaded, every blob on disk.
  Future<void> downloadMangaChapter(DownloadsStore store) async {
    final rowId = await store.ensureQueued(
      id: _id,
      chapterNumber: 12,
      title: 'The Weakest Hunter',
      seriesTitle: 'Solo Leveling',
    );
    await store.updateManifestInfo(rowId: rowId, pageCount: 3, chapterNumber: 12);
    for (var page = 1; page <= 3; page++) {
      await store.savePage(rowId: rowId, pageNumber: page, bytes: [page]);
    }
    expect(await store.markCompleteIfAllPagesPresent(rowId), isTrue);
  }

  group('the library (manifest-driven) reader', () {
    test(
      'a fully-downloaded chapter renders from disk without awaiting the '
      'manifest, even with the network reachable',
      () async {
        final store = harness.storeFor('u1p1');
        await downloadMangaChapter(store);

        final hanging = _HangingReaderRepository();
        when(
          () => hanging.manifest(
            sourceId: any(named: 'sourceId'),
            seriesKey: any(named: 'seriesKey'),
            chapterKey: any(named: 'chapterKey'),
          ),
        ).thenAnswer((_) => Completer<Result<ChapterManifest>>().future);

        final container = ProviderContainer(
          overrides: [
            readerRepositoryProvider.overrideWithValue(hanging),
            downloadsStoreProvider.overrideWithValue(store),
          ],
        );
        addTearDown(container.dispose);

        final resolved = await container
            .read(resolvedReaderChapterProvider(_id).future)
            .timeout(_patience);

        expect(resolved.isOffline, isTrue);
        expect(resolved.chapter.pages, hasLength(3));
        expect(
          resolved.chapter.pages.every((page) => page.localFile != null),
          isTrue,
          reason: 'every page must come from disk, not a proxy URL',
        );
        // The number progress is filed under survives the disk path — the
        // store stamped it at download time, so resuming still lands on
        // chapter 12 and not on "unknown".
        expect(resolved.chapterNumber, 12);
      },
    );

    test(
      'the manifest is never even asked for while the chapter is on disk',
      () async {
        final store = harness.storeFor('u1p1');
        await downloadMangaChapter(store);

        final hanging = _HangingReaderRepository();
        when(
          () => hanging.manifest(
            sourceId: any(named: 'sourceId'),
            seriesKey: any(named: 'seriesKey'),
            chapterKey: any(named: 'chapterKey'),
          ),
        ).thenAnswer((_) => Completer<Result<ChapterManifest>>().future);

        final container = ProviderContainer(
          overrides: [
            readerRepositoryProvider.overrideWithValue(hanging),
            downloadsStoreProvider.overrideWithValue(store),
          ],
        );
        addTearDown(container.dispose);

        await container
            .read(resolvedReaderChapterProvider(_id).future)
            .timeout(_patience);

        // Nothing in the content path touched the network. The neighbours
        // provider is where the manifest belongs now, and nobody asked it.
        verifyNever(
          () => hanging.manifest(
            sourceId: any(named: 'sourceId'),
            seriesKey: any(named: 'seriesKey'),
            chapterKey: any(named: 'chapterKey'),
          ),
        );
      },
    );

    test(
      'a PART-downloaded chapter still waits for the manifest — the pages on '
      'disk render from disk, only the gaps are fetched',
      () async {
        final store = harness.storeFor('u1p1');
        final rowId = await store.ensureQueued(id: _id);
        await store.updateManifestInfo(rowId: rowId, pageCount: 3);
        await store.savePage(rowId: rowId, pageNumber: 1, bytes: [1]);
        // Page 2 and 3 never arrived: nothing renderable end to end, so the
        // network is the only way to a complete chapter.

        final repo = _HangingReaderRepository();
        when(
          () => repo.manifest(
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
              chapterNumber: 12,
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
            readerRepositoryProvider.overrideWithValue(repo),
            downloadsStoreProvider.overrideWithValue(store),
          ],
        );
        addTearDown(container.dispose);

        final resolved = await container
            .read(resolvedReaderChapterProvider(_id).future)
            .timeout(_patience);

        expect(resolved.isOffline, isFalse);
        expect(resolved.chapter.pages[0].localFile, isNotNull); // the gap-free page
        expect(resolved.chapter.pages[1].localFile, isNull); // fetched
        expect(resolved.chapter.pages[2].localFile, isNull); // fetched
        expect(resolved.next, '2');
      },
    );

    test(
      'adjacent chapter keys arrive out of band, and never in front of the '
      'content',
      () async {
        final store = harness.storeFor('u1p1');
        await downloadMangaChapter(store);

        final repo = _HangingReaderRepository();
        when(
          () => repo.manifest(
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
              chapterNumber: 12,
              pageCount: 3,
              prev: '0',
              next: '2',
              pages: const [],
            ),
          ),
        );

        final container = ProviderContainer(
          overrides: [
            readerRepositoryProvider.overrideWithValue(repo),
            downloadsStoreProvider.overrideWithValue(store),
          ],
        );
        addTearDown(container.dispose);

        final resolved = await container
            .read(resolvedReaderChapterProvider(_id).future)
            .timeout(_patience);
        // The content answer itself carries no neighbours — it came off disk.
        expect(resolved.prev, isNull);
        expect(resolved.next, isNull);

        final neighbours =
            await container.read(chapterNeighboursProvider(_id).future);
        expect(neighbours.prev, '0');
        expect(neighbours.next, '2');
        expect(neighbours.chapterNumber, 12);
      },
    );
  });

  group('the source-browse reader', () {
    test(
      'the same downloaded chapter renders from disk here too, without '
      'awaiting the source payload',
      () async {
        final store = harness.storeFor('u1p1');
        await downloadMangaChapter(store);

        final hanging = _HangingSourcesRepository();
        when(() => hanging.getReaderChapter(any(), any(), any()))
            .thenAnswer((_) => Completer<Result<ReaderChapter>>().future);

        final container = ProviderContainer(
          overrides: [
            sourcesRepositoryProvider.overrideWithValue(hanging),
            downloadsStoreProvider.overrideWithValue(store),
          ],
        );
        addTearDown(container.dispose);

        final chapter = await container
            .read(
              sourceReaderChapterProvider(
                (
                  sourceId: _id.sourceId,
                  seriesId: _id.seriesKey,
                  chapterId: _id.chapterKey,
                ),
              ).future,
            )
            .timeout(_patience);

        expect(chapter.pages, hasLength(3));
        expect(chapter.pages.every((page) => page.localFile != null), isTrue);
        verifyNever(() => hanging.getReaderChapter(any(), any(), any()));
      },
    );
  });

  group('the novel reader', () {
    test(
      'a downloaded chapter of prose opens from disk without awaiting '
      '/novels/chapter',
      () async {
        final store = harness.storeFor('u1p1');
        final rowId = await store.ensureQueued(
          id: _id,
          chapterNumber: 12,
          kind: DownloadKind.novel,
        );
        await store.updateManifestInfo(rowId: rowId, pageCount: 1, chapterNumber: 12);
        await store.saveNovelText(
          rowId: rowId,
          chapter: const NovelChapter(
            sourceId: 'asura',
            seriesKey: 'solo-leveling',
            chapterKey: '1',
            chapterNumber: 12,
            title: 'Awakening',
            paragraphs: ['The gate opened.', 'Nobody came back.'],
            previousChapterKey: null,
            nextChapterKey: null,
            wordCount: 6,
          ).toStoredJson(),
        );
        expect(await store.markCompleteIfAllPagesPresent(rowId), isTrue);

        final hanging = _HangingNovelsRepository();
        when(
          () => hanging.chapter(
            sourceId: any(named: 'sourceId'),
            seriesKey: any(named: 'seriesKey'),
            chapterKey: any(named: 'chapterKey'),
          ),
        ).thenAnswer((_) => Completer<Result<NovelChapter>>().future);

        final container = ProviderContainer(
          overrides: [
            novelsRepositoryProvider.overrideWithValue(hanging),
            downloadsStoreProvider.overrideWithValue(store),
          ],
        );
        addTearDown(container.dispose);

        final chapter = await container
            .read(resolvedNovelChapterProvider(_id).future)
            .timeout(_patience);

        expect(chapter.isOffline, isTrue);
        expect(chapter.paragraphs, hasLength(2));
        expect(chapter.title, 'Awakening');
        verifyNever(
          () => hanging.chapter(
            sourceId: any(named: 'sourceId'),
            seriesKey: any(named: 'seriesKey'),
            chapterKey: any(named: 'chapterKey'),
          ),
        );
      },
    );
  });
}
