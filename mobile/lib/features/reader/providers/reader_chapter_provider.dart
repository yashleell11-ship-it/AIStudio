import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/reader/models/chapter_manifest.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

typedef ChapterManifestKey = ({
  String sourceId,
  String seriesKey,
  String chapterKey,
});

/// Fetches the source-native chapter manifest — page list plus adjacent
/// chapter keys — for the manifest-driven library reader.
final chapterManifestProvider = FutureProvider.autoDispose
    .family<ChapterManifest, ChapterManifestKey>((ref, key) async {
  final repo = ref.watch(readerRepositoryProvider);
  final result = await repo.manifest(
    sourceId: key.sourceId,
    seriesKey: key.seriesKey,
    chapterKey: key.chapterKey,
  );
  if (result.isErr) throw result.error;
  return result.value;
});
