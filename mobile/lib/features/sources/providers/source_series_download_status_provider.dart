import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_provider.dart';
import 'package:manhwamaniacs/features/downloads/utils/source_chapter_download_status.dart';

typedef SourceSeriesDownloadStatusKey = ({String sourceId, String seriesId});

final sourceSeriesChapterDownloadLookupProvider = Provider.autoDispose
    .family<SourceChapterDownloadLookup, SourceSeriesDownloadStatusKey>(
  (ref, key) {
    final downloadsState = ref.watch(downloadsProvider).valueOrNull;
    return buildSourceChapterDownloadLookup(
      sourceId: key.sourceId,
      seriesId: key.seriesId,
      items: downloadsState?.items ?? const [],
    );
  },
  name: 'sourceSeriesChapterDownloadLookup',
);
