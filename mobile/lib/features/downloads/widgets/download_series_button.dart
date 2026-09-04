import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/queue/download_queue_controller.dart';

/// "Download series" secondary action — queues every chapter in [chapters]
/// (already-downloaded or in-flight ones are a no-op via
/// [DownloadsStore.ensureQueued]'s own idempotency, so this never needs to
/// know which chapters are new).
///
/// Renders nothing with no active `(user, profile)` scope — there is no
/// store to queue into, and the per-chapter row buttons make the same call
/// (see `chapter_download_action.dart`), so the two controls always agree on
/// whether downloading is possible right now.
class DownloadSeriesButton extends ConsumerStatefulWidget {
  const DownloadSeriesButton({
    super.key,
    required this.chapters,
    this.label = 'Download Series',
  });

  final List<ChapterQueueRequest> chapters;

  /// What the control calls the whole thing. A book is not a "series" on the
  /// novel page, and the page that says "CONTENTS" over a table of contents
  /// should not offer to download a series.
  final String label;

  @override
  ConsumerState<DownloadSeriesButton> createState() => _DownloadSeriesButtonState();
}

class _DownloadSeriesButtonState extends ConsumerState<DownloadSeriesButton> {
  bool _queueing = false;

  Future<void> _queueAll() async {
    if (_queueing || widget.chapters.isEmpty) return;
    setState(() => _queueing = true);
    await ref.read(downloadQueueControllerProvider.notifier).enqueueChapters(widget.chapters);
    if (!mounted) return;
    setState(() => _queueing = false);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          widget.chapters.length == 1
              ? 'Queued 1 chapter for download.'
              : 'Queued ${widget.chapters.length} chapters for download.',
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final hasScope = ref.watch(activeDownloadsScopeIdProvider) != null;
    if (!hasScope) return const SizedBox.shrink();

    return OutlinedButton.icon(
      key: const Key('download-series'),
      onPressed: widget.chapters.isEmpty || _queueing ? null : _queueAll,
      icon: _queueing
          ? const SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          : const Icon(Icons.download_outlined),
      label: Text(widget.label),
      style: OutlinedButton.styleFrom(
        foregroundColor: context.colors.fg,
        side: BorderSide(color: context.colors.border),
        backgroundColor: context.colors.fg.withAlpha(13),
      ),
    );
  }
}
