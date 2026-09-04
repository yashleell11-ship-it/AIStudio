import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/features/downloads/models/download_chapter_state.dart';
import 'package:manhwamaniacs/features/downloads/models/saved_chapter.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/services/chapter_export.dart';

/// Human directions to what an export just wrote.
///
/// On iOS this is a *route through the Files app*, not a filesystem path,
/// because that is the only form of the answer the owner can act on:
/// `UIFileSharingEnabled` + `LSSupportsOpeningDocumentsInPlace`
/// (`ios/Runner/Info.plist`) put the app's Documents directory under
/// *On My iPhone → ManhwaManiacs*, and everything below it shows up there
/// exactly as named. Elsewhere the real path is the honest answer, since no
/// system file browser reaches app-private storage.
String exportLocationDescription(
  ChapterExportResult result,
  TargetPlatform platform,
) {
  if (platform == TargetPlatform.iOS) {
    return 'Files → On My iPhone → ManhwaManiacs → '
        '${ChapterExporter.exportsFolderName} → ${result.seriesFolderName}';
  }
  return result.directory.path;
}

/// Offers "Save to Files" for [chapters] and runs the chosen export.
///
/// The store keeps page bytes content-addressed — `mm-store/blobs/ab/<sha256>`
/// — which is right for dedup and refcounted deletion and useless to a human
/// browsing files. This is the presentation-layer answer: an on-demand,
/// readable copy, written only when asked for, that never touches the blob
/// tree or the index it is copied from.
Future<void> showDownloadExportSheet(
  BuildContext context,
  WidgetRef ref, {
  required String seriesLabel,
  required List<SavedChapter> chapters,
}) async {
  final ready = chapters
      .where((c) => c.state == DownloadChapterState.complete)
      .toList();
  final messenger = ScaffoldMessenger.of(context);
  if (ready.isEmpty) {
    messenger.showSnackBar(
      const SnackBar(
        content: Text(
          'Nothing to save yet — these chapters are still downloading.',
        ),
      ),
    );
    return;
  }

  final format = await showModalBottomSheet<ChapterExportFormat>(
    context: context,
    backgroundColor: context.colors.surfaceElevated,
    builder: (sheetContext) => SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.xl2,
              AppSpacing.xl2,
              AppSpacing.xl2,
              AppSpacing.sm,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Save to Files', style: AppTypography.h4),
                const SizedBox(height: AppSpacing.xs),
                Text(
                  ready.length == 1
                      ? 'Writes a readable copy of this chapter you can open '
                          'from the Files app. Your download stays where it is.'
                      : 'Writes readable copies of ${ready.length} downloaded '
                          'chapters you can open from the Files app. Your '
                          'downloads stay where they are.',
                  style: AppTypography.bodySm
                      .copyWith(color: context.colors.muted, height: 1.4),
                ),
              ],
            ),
          ),
          ListTile(
            key: const Key('export-format-images'),
            leading: Icon(
              Icons.photo_library_outlined,
              color: context.colors.primary,
            ),
            title: Text('Page images', style: AppTypography.labelLg),
            subtitle: Text(
              'A numbered folder per chapter. Tap any page to view it.',
              style: AppTypography.caption.copyWith(color: context.colors.muted),
            ),
            onTap: () =>
                Navigator.of(sheetContext).pop(ChapterExportFormat.images),
          ),
          ListTile(
            key: const Key('export-format-cbz'),
            leading: Icon(
              Icons.folder_zip_outlined,
              color: context.colors.primary,
            ),
            title: Text('CBZ file', style: AppTypography.labelLg),
            subtitle: Text(
              'One file per chapter, for comic reader apps.',
              style: AppTypography.caption.copyWith(color: context.colors.muted),
            ),
            onTap: () => Navigator.of(sheetContext).pop(ChapterExportFormat.cbz),
          ),
          const SizedBox(height: AppSpacing.sm),
        ],
      ),
    ),
  );
  if (format == null) return;

  final store = ref.read(downloadsStoreProvider);
  if (store == null) return;
  final exporter = ref.read(chapterExporterProvider);

  if (!context.mounted) return;
  // A modal barrier rather than a snackbar: copying a long series is real
  // I/O, and letting the user delete a chapter out from under the export
  // mid-run is the kind of race there is no good recovery from.
  unawaited(
    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (_) => const _ExportProgressDialog(),
    ),
  );

  ChapterExportResult? result;
  Object? failure;
  try {
    result = await exporter.export(
      store: store,
      seriesLabel: seriesLabel,
      chapters: ready,
      format: format,
    );
  } catch (error) {
    failure = error;
  }

  if (!context.mounted) return;
  Navigator.of(context, rootNavigator: true).pop(); // the progress dialog

  final exported = result;
  if (failure != null || exported == null) {
    messenger.showSnackBar(
      const SnackBar(
        content: Text('Could not save to Files. Check your free space.'),
      ),
    );
    return;
  }

  await showDialog<void>(
    context: context,
    builder: (dialogContext) => _ExportResultDialog(
      result: exported,
      platform: Theme.of(dialogContext).platform,
    ),
  );
}

class _ExportProgressDialog extends StatelessWidget {
  const _ExportProgressDialog();

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      backgroundColor: context.colors.surfaceElevated,
      content: Row(
        children: [
          const SizedBox(
            width: 20,
            height: 20,
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
          const SizedBox(width: AppSpacing.lg),
          Expanded(
            child: Text('Saving to Files…', style: AppTypography.body),
          ),
        ],
      ),
    );
  }
}

class _ExportResultDialog extends StatelessWidget {
  const _ExportResultDialog({required this.result, required this.platform});

  final ChapterExportResult result;
  final TargetPlatform platform;

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      backgroundColor: context.colors.surfaceElevated,
      title: Text(
        result.isEmpty ? 'Nothing to save' : 'Saved to Files',
        style: AppTypography.h4,
      ),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (result.isEmpty)
            Text(
              'None of those chapters are fully on this phone yet.',
              style: AppTypography.bodySm.copyWith(color: context.colors.muted),
            )
          else ...[
            Text(
              result.chapterCount == 1
                  ? '1 chapter · ${result.pageCount} pages'
                  : '${result.chapterCount} chapters · '
                      '${result.pageCount} pages',
              style: AppTypography.body,
            ),
            const SizedBox(height: AppSpacing.md),
            SelectableText(
              exportLocationDescription(result, platform),
              key: const Key('export-location'),
              style: AppTypography.bodySm.copyWith(
                color: context.colors.primary,
                height: 1.4,
              ),
            ),
          ],
          if (result.skippedCount > 0) ...[
            const SizedBox(height: AppSpacing.md),
            Text(
              result.skippedCount == 1
                  ? '1 chapter was skipped — it is not fully downloaded.'
                  : '${result.skippedCount} chapters were skipped — they are '
                      'not fully downloaded.',
              style: AppTypography.caption.copyWith(color: context.colors.muted),
            ),
          ],
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Done'),
        ),
      ],
    );
  }
}
