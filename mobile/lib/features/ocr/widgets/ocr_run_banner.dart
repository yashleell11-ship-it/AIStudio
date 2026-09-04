import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/features/ocr/controllers/ocr_run_controller.dart';
import 'package:manhwamaniacs/shared/widgets/glass_card.dart';

/// Live status for the current OCR run — the answer to spec §4's "must not
/// look frozen": a 60-page chapter is a minute of native work, so the page
/// counter, the determinate bar and the cancel button are the difference
/// between "working" and "hung".
///
/// Collapses to nothing when idle, and stays collapsed on a device with no
/// OCR engine (no run can ever start there, so [OcrRunPhase.idle] is
/// permanent).
class OcrRunBanner extends ConsumerWidget {
  const OcrRunBanner({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final run = ref.watch(ocrRunControllerProvider);
    if (run.phase == OcrRunPhase.idle) return const SizedBox.shrink();

    final (icon, color, message) = switch (run.phase) {
      OcrRunPhase.recognizing => (
          Icons.text_fields,
          context.colors.primary,
          run.totalPages > 0
              ? 'Extracting text — page ${run.completedPages} of ${run.totalPages}'
              : 'Extracting text…',
        ),
      OcrRunPhase.paused => (
          Icons.pause_circle_outline,
          context.colors.warning,
          'Text extraction pauses while the app is in the background — keep '
              'it open to continue.',
        ),
      OcrRunPhase.uploading => (
          Icons.cloud_upload_outlined,
          context.colors.primary,
          'Uploading the transcript…',
        ),
      OcrRunPhase.done => (
          Icons.check_circle_outline,
          context.colors.success,
          run.wordCount > 0
              ? 'Text extracted — ${run.wordCount} words are now searchable.'
              : 'Text extracted.',
        ),
      OcrRunPhase.cancelled => (
          Icons.cancel_outlined,
          context.colors.muted,
          'Text extraction cancelled.',
        ),
      OcrRunPhase.failed => (
          Icons.error_outline,
          context.colors.danger,
          run.message ?? 'Text extraction failed.',
        ),
      OcrRunPhase.idle => (Icons.text_fields, context.colors.muted, ''),
    };

    return Padding(
      padding: EdgeInsets.fromLTRB(
        context.space.xl2,
        context.space.lg,
        context.space.xl2,
        0,
      ),
      child: GlassCard(
        padding: EdgeInsets.all(context.space.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, color: color, size: 20),
                SizedBox(width: context.space.sm),
                Expanded(child: Text(message, style: context.text.bodySm)),
                if (run.isBusy)
                  TextButton(
                    key: const Key('ocr-cancel'),
                    onPressed: ref.read(ocrRunControllerProvider.notifier).cancel,
                    child: const Text('Cancel'),
                  ),
              ],
            ),
            if (run.phase == OcrRunPhase.recognizing ||
                run.phase == OcrRunPhase.paused) ...[
              SizedBox(height: context.space.sm),
              ClipRRect(
                borderRadius: BorderRadius.circular(context.radii.sm),
                child: LinearProgressIndicator(
                  value: run.progress,
                  minHeight: 3,
                  backgroundColor: context.colors.border,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
