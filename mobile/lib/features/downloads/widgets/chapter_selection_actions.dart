import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/features/downloads/models/chapter_identity.dart';
import 'package:manhwamaniacs/features/downloads/models/chapter_selection.dart';
import 'package:manhwamaniacs/features/downloads/models/saved_chapter.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/queue/download_queue_controller.dart';

/// Multi-select downloading for a series' chapter list — "download 10 chapters
/// in 1 go" (spec R4).
///
/// Two states in one slot. Idle it is a single "Select" button; active it is
/// the range helpers plus the count and the queue action. It lives in the
/// series page's secondary-actions row on both series pages, so the library
/// and the source catalog cannot drift into two different multi-selects.
///
/// **Every chapter goes through [DownloadQueueController.enqueueChapters]** —
/// the same call the per-row button and "Download Series" make. Selecting
/// forty chapters is therefore forty ordinary queue rows: the storage cap, the
/// ~1.5 GB free-space floor, pause/resume and per-item retry all apply exactly
/// as they do to one. There is deliberately no bulk path around the guards.
///
/// Renders nothing with no active `(user, profile)` scope, matching every
/// other download affordance: no store to queue into, no control that would
/// silently no-op.
class ChapterSelectionActions extends ConsumerWidget {
  const ChapterSelectionActions({
    super.key,
    required this.controller,
    required this.identity,
    required this.chaptersInReadingOrder,
    required this.seriesTitle,
    required this.kind,
  });

  final ChapterSelectionController controller;
  final SeriesIdentity identity;

  /// Oldest first, always — "next 10" means the next ten to *read*, which has
  /// nothing to do with which way the visible list is currently sorted.
  final List<SelectableChapter> chaptersInReadingOrder;

  final String seriesTitle;

  /// Page images or prose: decides which endpoint the queue fetches and which
  /// reader the finished row opens in.
  final DownloadKind kind;

  Future<void> _queueSelected(BuildContext context, WidgetRef ref) async {
    final selected = controller.selected;
    if (selected.isEmpty) return;
    final requests = <ChapterQueueRequest>[
      for (final chapter in chaptersInReadingOrder)
        if (selected.contains(chapter.key))
          (
            id: (
              sourceId: identity.sourceId,
              seriesKey: identity.seriesKey,
              chapterKey: chapter.key,
            ),
            chapterNumber: chapter.number,
            title: chapter.title,
            seriesTitle: seriesTitle,
            kind: kind,
          ),
    ];
    final messenger = ScaffoldMessenger.of(context);
    controller.end();
    await ref
        .read(downloadQueueControllerProvider.notifier)
        .enqueueChapters(requests);
    messenger.showSnackBar(
      SnackBar(
        content: Text(
          requests.length == 1
              ? 'Queued 1 chapter for download.'
              : 'Queued ${requests.length} chapters for download.',
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (ref.watch(activeDownloadsScopeIdProvider) == null) {
      return const SizedBox.shrink();
    }
    if (chaptersInReadingOrder.isEmpty) return const SizedBox.shrink();

    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        if (!controller.isActive) {
          return OutlinedButton.icon(
            key: const Key('select-chapters'),
            onPressed: controller.begin,
            icon: const Icon(Icons.checklist_rounded),
            label: const Text('Select'),
            style: OutlinedButton.styleFrom(
              foregroundColor: context.colors.fg,
              side: BorderSide(color: context.colors.border),
              backgroundColor: context.colors.fg.withAlpha(13),
            ),
          );
        }
        return _SelectionBar(
          controller: controller,
          chaptersInReadingOrder: chaptersInReadingOrder,
          onDownload: () => _queueSelected(context, ref),
        );
      },
    );
  }
}

/// The active bar: the ranges first, because picking ten rows by hand is the
/// thing being replaced and a bare set of checkboxes would just be that with
/// extra steps.
class _SelectionBar extends StatelessWidget {
  const _SelectionBar({
    required this.controller,
    required this.chaptersInReadingOrder,
    required this.onDownload,
  });

  final ChapterSelectionController controller;
  final List<SelectableChapter> chaptersInReadingOrder;
  final VoidCallback onDownload;

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    final count = controller.count;
    final nextTen = nextUnreadUndownloadedKeys(chaptersInReadingOrder);
    final allUnread = unreadUndownloadedKeys(chaptersInReadingOrder);
    final everything = undownloadedKeys(chaptersInReadingOrder);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(AppRadius.lg),
        border: Border.all(color: colors.border),
        color: colors.fg.withAlpha(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: AppSpacing.sm,
            runSpacing: AppSpacing.sm,
            children: [
              _RangeChip(
                chipKey: const Key('select-next-10'),
                // Named with the real number rather than "Next 10" when the
                // series has fewer left: a control that promises ten and hands
                // over three reads as a failure.
                label: nextTen.length == kQuickRangeChapterCount
                    ? 'Next $kQuickRangeChapterCount'
                    : 'Next ${nextTen.length}',
                onTap: nextTen.isEmpty
                    ? null
                    : () => controller.replaceWith(nextTen),
              ),
              _RangeChip(
                chipKey: const Key('select-all-unread'),
                label: 'All unread (${allUnread.length})',
                onTap: allUnread.isEmpty
                    ? null
                    : () => controller.replaceWith(allUnread),
              ),
              _RangeChip(
                chipKey: const Key('select-all-chapters'),
                label: 'All (${everything.length})',
                onTap: everything.isEmpty
                    ? null
                    : () => controller.replaceWith(everything),
              ),
              _RangeChip(
                chipKey: const Key('select-none'),
                label: 'None',
                onTap: count == 0 ? null : controller.clearSelection,
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.md),
          Row(
            children: [
              Expanded(
                child: FilledButton.icon(
                  key: const Key('download-selected'),
                  onPressed: count == 0 ? null : onDownload,
                  icon: const Icon(Icons.download_rounded),
                  label: Text(
                    count == 0
                        ? 'Select chapters'
                        : count == 1
                            ? 'Download 1 chapter'
                            : 'Download $count chapters',
                  ),
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              TextButton(
                key: const Key('cancel-selection'),
                onPressed: controller.end,
                child: const Text('Cancel'),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _RangeChip extends StatelessWidget {
  const _RangeChip({
    required this.chipKey,
    required this.label,
    required this.onTap,
  });

  final Key chipKey;
  final String label;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return ActionChip(
      key: chipKey,
      label: Text(label),
      onPressed: onTap,
      // A range with nothing left to offer stays visible and greyed rather
      // than disappearing: the row must not reflow as chapters are queued.
      backgroundColor: onTap == null
          ? context.colors.fg.withAlpha(8)
          : context.colors.fg.withAlpha(20),
      side: BorderSide(color: context.colors.border),
      labelStyle: TextStyle(
        color: onTap == null ? context.colors.muted : context.colors.fg,
      ),
    );
  }
}
