import 'package:aistudio_mobile/features/reader/models/reader_chapter.dart';
import 'package:aistudio_mobile/shared/providers/repository_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Arguments for [sourceReaderChapterProvider].
class SourceReaderChapterArgs {
  const SourceReaderChapterArgs({
    required this.sourceId,
    required this.seriesId,
    required this.chapterId,
  });

  final String sourceId;
  final String seriesId;
  final String chapterId;

  @override
  bool operator ==(Object other) =>
      other is SourceReaderChapterArgs &&
      other.sourceId == sourceId &&
      other.seriesId == seriesId &&
      other.chapterId == chapterId;

  @override
  int get hashCode => Object.hash(sourceId, seriesId, chapterId);
}

/// Fetches the unified reader payload for an online source chapter.
final sourceReaderChapterProvider = FutureProvider.autoDispose
    .family<ReaderChapter, SourceReaderChapterArgs>((ref, args) async {
  final repo = ref.watch(sourcesRepositoryProvider);
  final result = await repo.getReaderChapter(
    args.sourceId,
    args.seriesId,
    args.chapterId,
  );
  if (result.isErr) throw result.error;
  return result.value;
});
