import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/reader/models/reader_chapter.dart';
import 'package:manhwamaniacs/features/sources/utils/source_reader_offline.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

typedef SourceReaderChapterKey = ({String sourceId, String seriesId, String chapterId});

/// Fetches the unified reader payload for an online source chapter.
///
/// When the online fetch fails, attempts to open a completed local download
/// for the same source chapter before surfacing the error.
final sourceReaderChapterProvider = FutureProvider.autoDispose
    .family<ReaderChapter, SourceReaderChapterKey>((ref, key) async {
  final repo = ref.watch(sourcesRepositoryProvider);
  final result = await repo.getReaderChapter(
    key.sourceId,
    key.seriesId,
    key.chapterId,
  );
  if (result.isOk) return result.value;

  final offline = await resolveSourceReaderOfflineHandoff(
    downloadsRepository: ref.read(downloadsRepositoryProvider),
    libraryRepository: ref.read(libraryRepositoryProvider),
    sourceId: key.sourceId,
    seriesId: key.seriesId,
    chapterId: key.chapterId,
  );
  if (offline != null) {
    // The handoff already fetched the ChapterDetail while resolving the local
    // ids; map it straight through instead of a redundant second getChapter on
    // exactly this dead/blocked-source failure path.
    return readerChapterFromLibraryDetail(
      offline.chapter,
      ref.read(apiBaseUrlProvider),
    );
  }

  throw result.error;
});
