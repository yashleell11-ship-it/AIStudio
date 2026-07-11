import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/updates/models/series_tracker.dart';
import 'package:manhwamaniacs/features/updates/models/update_notification.dart';
import 'package:manhwamaniacs/features/updates/providers/updates_provider.dart';
import 'package:manhwamaniacs/shared/widgets/empty_state.dart';
import 'package:manhwamaniacs/shared/widgets/glass_card.dart';
import 'package:manhwamaniacs/shared/widgets/skeleton_box.dart';

class UpdatesScreen extends ConsumerWidget {
  const UpdatesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final updatesAsync = ref.watch(updatesProvider);
    final notifier = ref.read(updatesProvider.notifier);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Updates'),
        actions: [
          IconButton(
            tooltip: 'Check now',
            onPressed: notifier.triggerCheck,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: updatesAsync.when(
        loading: () => const _UpdatesSkeleton(),
        error: (error, _) => _UpdatesError(
          error: error is AppError
              ? error
              : UnknownError(message: error.toString(), cause: error),
          onRetry: notifier.refresh,
        ),
        data: (state) => RefreshIndicator(
          color: AppColors.primary,
          onRefresh: notifier.refresh,
          child: ListView(
            padding: const EdgeInsets.all(AppSpacing.xl2),
            children: [
              Text('Updates', style: AppTypography.displayMd),
              const SizedBox(height: AppSpacing.xs),
              Text(
                '${state.unreadCount} unread · ${state.trackers.length} tracked series',
                style: AppTypography.body.copyWith(color: AppColors.muted),
              ),
              const SizedBox(height: AppSpacing.xl2),
              Wrap(
                spacing: AppSpacing.sm,
                runSpacing: AppSpacing.sm,
                children: [
                  FilledButton.icon(
                    onPressed: notifier.triggerCheck,
                    icon: const Icon(Icons.sync, size: 16),
                    label: const Text('Check all now'),
                  ),
                  if (state.unreadCount > 0)
                    OutlinedButton.icon(
                      onPressed: notifier.markAllRead,
                      icon: const Icon(Icons.done_all, size: 16),
                      label: const Text('Mark all read'),
                    ),
                ],
              ),
              const SizedBox(height: AppSpacing.xl2),
              const _SectionHeader(title: 'Notifications'),
              const SizedBox(height: AppSpacing.md),
              if (state.notifications.isEmpty)
                const EmptyState(
                  icon: Icons.notifications_none,
                  message: 'No update notifications',
                  subtitle: 'Follow series or sync downloads to get notified.',
                )
              else
                ...state.notifications.map(
                  (notification) => Padding(
                    padding: const EdgeInsets.only(bottom: AppSpacing.md),
                    child: _NotificationCard(
                      notification: notification,
                      onMarkRead: notification.isRead
                          ? null
                          : () => notifier.markRead(notification.id),
                    ),
                  ),
                ),
              const SizedBox(height: AppSpacing.xl2),
              const _SectionHeader(title: 'Tracked series'),
              const SizedBox(height: AppSpacing.md),
              if (state.trackers.isEmpty)
                const EmptyState(
                  icon: Icons.rss_feed,
                  message: 'No tracked series',
                  subtitle: 'Track series from sources to monitor new chapters.',
                )
              else
                ...state.trackers.map(
                  (tracker) => Padding(
                    padding: const EdgeInsets.only(bottom: AppSpacing.md),
                    child: _TrackerCard(
                      tracker: tracker,
                      actionPending: state.actionPending,
                      onDelete: () => notifier.deleteTracker(tracker.id),
                      onAutoDownloadChanged: tracker.trackKind == TrackKind.followed
                          ? (enabled) =>
                              notifier.setTrackerAutoDownload(tracker.id, enabled)
                          : null,
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({required this.title});

  final String title;

  @override
  Widget build(BuildContext context) {
    return Text(title, style: AppTypography.h3);
  }
}

class _NotificationCard extends StatelessWidget {
  const _NotificationCard({
    required this.notification,
    this.onMarkRead,
  });

  final UpdateNotification notification;
  final VoidCallback? onMarkRead;

  @override
  Widget build(BuildContext context) {
    final date = notification.createdAt != null
        ? DateFormat.yMMMd().add_jm().format(notification.createdAt!.toLocal())
        : null;

    return GlassCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  notification.seriesTitle,
                  style: AppTypography.labelLg,
                ),
              ),
              if (!notification.isRead)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: AppColors.primary.withAlpha(51),
                    borderRadius: BorderRadius.circular(999),
                  ),
                  child: Text(
                    'NEW',
                    style: AppTypography.caption.copyWith(color: AppColors.primary),
                  ),
                ),
            ],
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            notification.chapterTitle,
            style: AppTypography.body.copyWith(color: AppColors.muted),
          ),
          if (date != null) ...[
            const SizedBox(height: AppSpacing.xs),
            Text(date, style: AppTypography.caption),
          ],
          if (onMarkRead != null) ...[
            const SizedBox(height: AppSpacing.md),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton(onPressed: onMarkRead, child: const Text('Mark read')),
            ),
          ],
        ],
      ),
    );
  }
}

class _TrackerCard extends StatelessWidget {
  const _TrackerCard({
    required this.tracker,
    required this.onDelete,
    this.onAutoDownloadChanged,
    this.actionPending = false,
  });

  final SeriesTracker tracker;
  final VoidCallback onDelete;
  final ValueChanged<bool>? onAutoDownloadChanged;
  final bool actionPending;

  @override
  Widget build(BuildContext context) {
    return GlassCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(child: Text(tracker.seriesTitle, style: AppTypography.labelLg)),
              Chip(
                label: Text(
                  tracker.trackKind == TrackKind.followed ? 'Followed' : 'Downloaded',
                  style: AppTypography.caption,
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            '${tracker.source} · ${tracker.knownChapterCount} chapters',
            style: AppTypography.body.copyWith(color: AppColors.muted),
          ),
          if (tracker.lastError != null) ...[
            const SizedBox(height: AppSpacing.xs),
            Text(
              tracker.lastError!,
              style: AppTypography.caption.copyWith(color: AppColors.warning),
            ),
          ],
          if (onAutoDownloadChanged != null) ...[
            const SizedBox(height: AppSpacing.sm),
            Material(
              type: MaterialType.transparency,
              child: SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Auto download new chapters'),
                value: tracker.autoDownload,
                onChanged: actionPending ? null : onAutoDownloadChanged,
              ),
            ),
          ],
          Align(
            alignment: Alignment.centerRight,
            child: TextButton(
              onPressed: actionPending ? null : onDelete,
              child: const Text('Remove'),
            ),
          ),
        ],
      ),
    );
  }
}

class _UpdatesSkeleton extends StatelessWidget {
  const _UpdatesSkeleton();

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(AppSpacing.xl2),
      children: const [
        SkeletonBox(width: 180, height: 36),
        SizedBox(height: AppSpacing.xl2),
        SkeletonBox(width: double.infinity, height: 100),
        SizedBox(height: AppSpacing.md),
        SkeletonBox(width: double.infinity, height: 100),
      ],
    );
  }
}

class _UpdatesError extends StatelessWidget {
  const _UpdatesError({required this.error, required this.onRetry});

  final AppError error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(error.userMessage, style: AppTypography.body.copyWith(color: AppColors.danger)),
          const SizedBox(height: AppSpacing.lg),
          FilledButton(onPressed: onRetry, child: const Text('Retry')),
        ],
      ),
    );
  }
}