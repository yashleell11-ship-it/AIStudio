import 'package:aistudio_mobile/app/theme/app_colors.dart';
import 'package:aistudio_mobile/app/theme/app_spacing.dart';
import 'package:aistudio_mobile/app/theme/app_typography.dart';
import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/features/downloads/models/download_item.dart';
import 'package:aistudio_mobile/features/downloads/providers/downloads_provider.dart';
import 'package:aistudio_mobile/features/downloads/utils/download_grouping.dart';
import 'package:aistudio_mobile/features/downloads/widgets/downloads_skeleton.dart';
import 'package:aistudio_mobile/features/downloads/widgets/downloads_widgets.dart';
import 'package:aistudio_mobile/features/reader/utils/local_reader_handoff.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class DownloadsScreen extends ConsumerStatefulWidget {
  const DownloadsScreen({super.key});

  @override
  ConsumerState<DownloadsScreen> createState() => _DownloadsScreenState();
}

class _DownloadsScreenState extends ConsumerState<DownloadsScreen> {
  var _completedOpen = true;

  @override
  Widget build(BuildContext context) {
    final downloadsAsync = ref.watch(downloadsProvider);
    final filter = ref.watch(downloadFilterProvider);
    final notifier = ref.read(downloadsProvider.notifier);

    return Scaffold(
      appBar: AppBar(title: const Text('Downloads')),
      body: downloadsAsync.when(
        loading: () => const DownloadsSkeleton(),
        error: (error, _) => _DownloadsError(
          error: error is AppError
              ? error
              : UnknownError(message: error.toString(), cause: error),
          onRetry: notifier.refresh,
        ),
        data: (state) => RefreshIndicator(
          onRefresh: notifier.refresh,
          color: AppColors.primary,
          child: CustomScrollView(
            physics: const AlwaysScrollableScrollPhysics(),
            slivers: [
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.all(AppSpacing.xl2),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Text('Downloads', style: AppTypography.displayMd),
                          const SizedBox(height: AppSpacing.xs),
                          Text(
                            '${state.metrics.active + state.metrics.queued + state.metrics.paused} active, ${state.metrics.completed} completed',
                            style: AppTypography.body.copyWith(color: AppColors.muted),
                          ),
                          const SizedBox(height: AppSpacing.lg),
                          Wrap(
                            spacing: AppSpacing.sm,
                            runSpacing: AppSpacing.sm,
                            children: [
                              OutlinedButton.icon(
                                onPressed: state.actionPending || state.items.isEmpty
                                    ? null
                                    : notifier.pauseAll,
                                icon: const Icon(Icons.pause, size: 16),
                                label: const Text('Pause All'),
                              ),
                              OutlinedButton.icon(
                                onPressed: state.actionPending || state.items.isEmpty
                                    ? null
                                    : notifier.resumeAll,
                                icon: const Icon(Icons.play_arrow, size: 16),
                                label: const Text('Resume All'),
                              ),
                              TextButton.icon(
                                onPressed: state.actionPending || state.items.isEmpty
                                    ? null
                                    : notifier.cancelAll,
                                icon: const Icon(Icons.close, size: 16),
                                label: const Text('Cancel All'),
                                style: TextButton.styleFrom(
                                  foregroundColor: AppColors.danger,
                                ),
                              ),
                            ],
                          ),
                        ],
                      ),
                      if (state.feedbackMessage != null) ...[
                        const SizedBox(height: AppSpacing.md),
                        _FeedbackBanner(message: state.feedbackMessage!),
                      ],
                      if (state.actionError != null) ...[
                        const SizedBox(height: AppSpacing.md),
                        _ErrorBanner(message: state.actionError!.userMessage),
                      ],
                      const SizedBox(height: AppSpacing.xl2),
                      DownloadsMetricsPanel(metrics: state.metrics),
                      const SizedBox(height: AppSpacing.xl2),
                      DownloadFilterChips(
                        items: state.items,
                        activeFilter: filter,
                        onChanged: (value) =>
                            ref.read(downloadFilterProvider.notifier).state = value,
                      ),
                      const SizedBox(height: AppSpacing.xl2),
                      ..._buildQueueContent(state, filter, notifier),
                      ..._buildCompletedSection(state.items),
                      const SizedBox(height: AppSpacing.xl3),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  List<Widget> _buildQueueContent(
    DownloadsState state,
    DownloadFilterTab filter,
    DownloadsNotifier notifier,
  ) {
    final queueItems = state.items
        .where((item) => !hiddenFromQueue.contains(item.status))
        .toList();
    final groups = groupDownloadsBySeries(state.items)
        .where(
          (group) => visibleGroupItems(group)
              .any((item) => matchesDownloadFilter(item, filter)),
        )
        .toList();

    if (state.items.isEmpty) {
      return const [
        DownloadsEmptyPanel(
          message: 'No downloads yet',
          subtitle: 'Queue chapters from any source connector.',
        ),
      ];
    }

    if (queueItems.isEmpty) {
      return const [
        DownloadsEmptyPanel(
          message: 'All caught up',
          subtitle: 'No active downloads in the queue.',
        ),
      ];
    }

    if (groups.isEmpty) {
      return const [
        DownloadsEmptyPanel(
          message: 'No downloads match this filter',
          subtitle: 'Try a different filter tab.',
        ),
      ];
    }

    return [
      for (final group in groups) ...[
        SeriesGroupCard(
          group: group,
          filter: filter,
          busy: state.actionPending,
          onPauseSeries: () => notifier.pauseSeries(group.source, group.seriesId),
          onResumeSeries: () => notifier.resumeSeries(group.source, group.seriesId),
          onCancelSeries: () => notifier.cancelSeries(group.source, group.seriesId),
          onPauseItem: notifier.pauseItem,
          onResumeItem: notifier.resumeItem,
          onCancelItem: notifier.cancelItem,
          onRetryItem: notifier.retryItem,
        ),
        const SizedBox(height: AppSpacing.lg),
      ],
    ];
  }

  List<Widget> _buildCompletedSection(List<DownloadItem> items) {
    final completedItems =
        items.where((item) => item.isCompleted).toList(growable: false);
    if (completedItems.isEmpty) return const [];

    return [
      InkWell(
        onTap: () => setState(() => _completedOpen = !_completedOpen),
        child: Row(
          children: [
            Text(
              'Completed (${completedItems.length})',
              style: AppTypography.labelLg.copyWith(fontWeight: FontWeight.w600),
            ),
            const SizedBox(width: AppSpacing.sm),
            Icon(
              _completedOpen ? Icons.expand_less : Icons.expand_more,
              color: AppColors.muted,
            ),
          ],
        ),
      ),
      if (_completedOpen) ...[
        const SizedBox(height: AppSpacing.md),
        for (final item in completedItems) ...[
          CompletedDownloadRow(
            item: item,
            onTap: item.localChapterId != null
                ? () => openDownloadedChapter(context, ref, item)
                : null,
          ),
          const SizedBox(height: AppSpacing.sm),
        ],
      ],
      const SizedBox(height: AppSpacing.xl2),
    ];
  }
}

class _DownloadsError extends StatelessWidget {
  const _DownloadsError({required this.error, required this.onRetry});

  final AppError error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.xl3),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, color: AppColors.danger, size: 48),
            const SizedBox(height: AppSpacing.lg),
            Text(
              'Failed to load downloads',
              style: AppTypography.h3,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: AppSpacing.sm),
            Text(
              error.userMessage,
              style: AppTypography.body.copyWith(color: AppColors.muted),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: AppSpacing.xl2),
            FilledButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('Try Again'),
            ),
          ],
        ),
      ),
    );
  }
}

class _FeedbackBanner extends StatelessWidget {
  const _FeedbackBanner({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.success.withAlpha(26),
        borderRadius: BorderRadius.circular(AppRadius.lg),
        border: Border.all(color: AppColors.success.withAlpha(77)),
      ),
      child: Text(message, style: AppTypography.bodySm),
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.danger.withAlpha(26),
        borderRadius: BorderRadius.circular(AppRadius.lg),
        border: Border.all(color: AppColors.danger.withAlpha(77)),
      ),
      child: Text(
        message,
        style: AppTypography.bodySm.copyWith(color: AppColors.danger),
      ),
    );
  }
}
