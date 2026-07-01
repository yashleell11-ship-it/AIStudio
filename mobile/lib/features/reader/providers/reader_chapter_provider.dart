import 'package:aistudio_mobile/features/library/models/chapter.dart';
import 'package:aistudio_mobile/features/reader/models/adjacent_chapter.dart';
import 'package:aistudio_mobile/shared/providers/repository_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

final readerChapterProvider =
    FutureProvider.autoDispose.family<ChapterDetail, int>((ref, chapterId) async {
  final repo = ref.watch(libraryRepositoryProvider);
  final result = await repo.getChapter(chapterId);
  if (result.isErr) throw result.error;
  return result.value;
});

final adjacentChapterProvider = FutureProvider.autoDispose
    .family<AdjacentChapter?, ({int chapterId, String direction})>((ref, args) async {
  final repo = ref.watch(libraryRepositoryProvider);
  final result = await repo.getAdjacentChapter(
    args.chapterId,
    direction: args.direction,
  );
  if (result.isErr) throw result.error;
  return result.value;
});
