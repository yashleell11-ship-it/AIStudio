import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/features/downloads/models/download_chapter_state.dart';
import 'package:manhwamaniacs/features/downloads/models/saved_chapter.dart';
import 'package:manhwamaniacs/features/ocr/controllers/ocr_run_controller.dart';
import 'package:manhwamaniacs/features/ocr/providers/ocr_providers.dart';

/// The per-chapter "extract text" control on the Downloads screen.
///
/// Renders nothing at all in three cases, each for the same reason — spec §4's
/// rule that a missing platform impl means a hidden feature, not a broken
/// button:
///
/// 1. No platform OCR engine on this device.
/// 2. The chapter isn't fully downloaded. OCR reads page files off disk; a
///    queued or failed chapter has nothing to read, and downloading pages
///    *in order to* OCR them is explicitly not what this feature does.
/// 3. Another chapter's run is in flight — one run at a time (see
///    [OcrRunController]), so offering a second button that would silently
///    do nothing is worse than offering none.
class OcrChapterAction extends ConsumerWidget {
  const OcrChapterAction({super.key, required this.chapter});

  final SavedChapter chapter;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (!ref.watch(ocrFeatureVisibleProvider)) return const SizedBox.shrink();
    if (chapter.state != DownloadChapterState.complete) {
      return const SizedBox.shrink();
    }

    final id = chapter.identity;
    final run = ref.watch(ocrRunControllerProvider);
    final isThisChapter = run.chapter == id;

    if (run.isBusy) {
      return isThisChapter
          ? const Padding(
              padding: EdgeInsets.symmetric(horizontal: 14),
              child: SizedBox(
                width: 16,
                height: 16,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
            )
          : const SizedBox.shrink();
    }

    final coverage = ref
        .watch(
          ocrCoverageProvider(
            (sourceId: id.sourceId, seriesKey: id.seriesKey),
          ),
        )
        .valueOrNull;
    // Unresolved coverage reads as "not covered": offering the action while
    // the answer is still in flight is harmless (the backend upserts, so a
    // redundant run costs time and nothing else), whereas hiding it would
    // make the row flicker on every screen build.
    final covered = coverage?.covers(id.chapterKey) ?? false;

    return IconButton(
      key: Key('ocr-${id.sourceId}-${id.seriesKey}-${id.chapterKey}'),
      tooltip: covered
          ? 'Text already extracted — tap to redo'
          : 'Extract text (OCR)',
      icon: Icon(
        covered ? Icons.text_snippet : Icons.text_fields,
        size: 20,
        color: covered ? AppColors.success : AppColors.muted,
      ),
      onPressed: () => ref.read(ocrRunControllerProvider.notifier).runChapter(
            id: id,
            chapterNumber: chapter.chapterNumber,
          ),
    );
  }
}
