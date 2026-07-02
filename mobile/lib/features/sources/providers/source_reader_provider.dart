import 'package:aistudio_mobile/features/reader/models/reader_chapter.dart';
import 'package:aistudio_mobile/features/sources/providers/source_reader_provider.dart';
import 'package:aistudio_mobile/features/sources/utils/source_reader_offline.dart';
import 'package:aistudio_mobile/shared/providers/core_providers.dart';
import 'package:aistudio_mobile/shared/providers/repository_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Fetches the unified reader payload for an online source chapter.
///
/// When the online fetch fails, attempts to open a completed local download
/// for the same source chapter before surfacing the error.
final sourceReaderChapterProvider = FutureProvider.autoDispose
    .family<ReaderChapter, SourceReaderChapterArgs>((ref, args) async {
  final repo = ref.watch(sourcesRepositoryProvider);
  final result = await repo.getReaderChapter(
    args.sourceId,
    args.seriesId,
    args.chapterId,
  );
  if (result.isOk) return result.value;

  final offline = await resolveSourceReaderOfflineHandoff(
    downloadsRepository: ref.read(downloadsRepositoryProvider),
    libraryRepository: ref.read(libraryRepositoryProvider),
    args: args,
  );
  if (offline != null) {
    final chapterResult =
        await ref.read(libraryRepositoryProvider).getChapter(offline.chapterId);
    if (chapterResult.isOk) {
      return readerChapterFromLibraryDetail(
        chapterResult.value,
        ref.read(apiBaseUrlProvider),
      );
    }
  }

  throw result.error;
});
