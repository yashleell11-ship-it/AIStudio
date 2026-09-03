import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/reader/models/reader_chapter.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

typedef SourceReaderChapterKey = ({String sourceId, String seriesId, String chapterId});

/// Fetches the unified reader payload for an online source chapter.
// TODO(1c-M3): fall back to a completed on-device download when the online
// fetch fails, once the on-device store ships.
final sourceReaderChapterProvider = FutureProvider.autoDispose
    .family<ReaderChapter, SourceReaderChapterKey>((ref, key) async {
  final repo = ref.watch(sourcesRepositoryProvider);
  final result = await repo.getReaderChapter(
    key.sourceId,
    key.seriesId,
    key.chapterId,
  );
  if (result.isOk) return result.value;
  throw result.error;
});
