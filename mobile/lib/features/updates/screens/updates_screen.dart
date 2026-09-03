import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/library/models/followed_series.dart';
import 'package:manhwamaniacs/features/updates/models/update_notification.dart';
import 'package:manhwamaniacs/features/updates/providers/updates_provider.dart';
import 'package:manhwamaniacs/shared/widgets/empty_state.dart';
import 'package:manhwamaniacs/shared/widgets/premium/fade_in.dart';
import 'package:manhwamaniacs/shared/widgets/premium/ghost_pill_button.dart';
import 'package:manhwamaniacs/shared/widgets/premium/glass_panel.dart';
import 'package:manhwamaniacs/shared/widgets/premium/hero_heading.dart';
import 'package:manhwamaniacs/shared/widgets/premium/primary_pill_button.dart';
import 'package:manhwamaniacs/shared/widgets/skeleton_box.dart';

class UpdatesScreen extends ConsumerWidget {
  const UpdatesScreen({super.key});

  /// Awaits an action that returns an [AppError] on failure and surfaces it as
  /// a SnackBar. Silent on success.
  Future<void> _run(BuildContext context, Future<AppError?> action) async {
    final error = await action;
    if (error != null && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.userMessage)),
      );
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final updatesAsync = ref.watch(updatesProvider);
    final notifier = ref.read(updatesProvider.notifier);

    return Scaffold(
      backgroundColor: AppColors.bg,
      appBar: AppBar(
        backgroundColor: AppColors.bg,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          tooltip: 'Back',
          onPressed: () =>
              context.canPop() ? context.pop() : context.go(Routes.more),
        ),
        title: Text('Updates', style: AppTypography.h3),
        actions: [
          IconButton(
            tooltip: 'Check now',
            color: AppColors.primary,
            onPressed: () => _run(context, notifier.triggerCheck()),
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
              FadeIn(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const HeroHeading(text: 'Updates', fontSize: 40),
                    const SizedBox(height: AppSpacing.xs),
                    Text(
                      '${state.unreadCount} unread · ${state.followed.length} followed series',
                      style: AppTypography.body.copyWith(color: AppColors.muted),
                    ),
                    const SizedBox(height: AppSpacing.xl2),
                    Wrap(
                      spacing: AppSpacing.sm,
                      runSpacing: AppSpacing.sm,
                      children: [
                        PrimaryPillButton(
                          label: 'Check all now',
                          icon: Icons.sync,
                          onPressed: () =>
                              _run(context, notifier.triggerCheck()),
                        ),
                        if (state.unreadCount > 0)
                          GhostPillButton(
                            label: 'Mark all read',
                            icon: Icons.done_all,
                            onPressed: () =>
                                _run(context, notifier.markAllRead()),
                          ),
                      ],
                    ),
                  ],
                ),
              ),
              const SizedBox(height: AppSpacing.xl2),
              const _SectionHeader(title: 'Notifications'),
              const SizedBox(height: AppSpacing.md),
              if (state.notifications.isEmpty)
                const EmptyState(
                  icon: Icons.notifications_none,
                  message: 'No update notifications',
                  subtitle: 'Follow series to get notified of new chapters.',
                )
              else
                ...state.notifications.map(
                  (notification) => Padding(
                    padding: const EdgeInsets.only(bottom: AppSpacing.md),
                    child: _NotificationCard(
                      notification: notification,
                      onMarkRead: notification.isRead
                          ? null
                          : () => _run(
                              context,
                              notifier.markRead(notification.id),
                            ),
                    ),
                  ),
                ),
              const SizedBox(height: AppSpacing.xl2),
              const _SectionHeader(title: 'Followed series'),
              const SizedBox(height: AppSpacing.md),
              if (state.followed.isEmpty)
                const EmptyState(
                  icon: Icons.rss_feed,
                  message: 'No followed series',
                  subtitle: 'Follow series from sources to monitor new chapters.',
                )
              else
                ...state.followed.map(
                  (series) => Padding(
                    padding: const EdgeInsets.only(bottom: AppSpacing.md),
                    child: _FollowedSeriesCard(
                      series: series,
                      actionPending: state.actionPending,
                      onRemove: () =>
                          _run(context, notifier.unfollow(series.id)),
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
    return Row(
      children: [
        Container(
          width: 3,
          height: 18,
          decoration: BoxDecoration(
            color: AppColors.primary,
            borderRadius: BorderRadius.circular(AppRadius.full),
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        Text(title, style: AppTypography.h3),
      ],
    );
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

    return GlassPanel(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  notification.chapterTitle,
                  style: AppTypography.labelLg,
                ),
              ),
              if (!notification.isRead) const _NewBadge(),
            ],
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            notification.sourceId,
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
              child: TextButton(
                onPressed: onMarkRead,
                style: TextButton.styleFrom(foregroundColor: AppColors.primary),
                child: const Text('Mark read'),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _NewBadge extends StatelessWidget {
  const _NewBadge();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: AppColors.primary.withValues(alpha: 0.20),
        borderRadius: BorderRadius.circular(AppRadius.full),
        border: Border.all(color: AppColors.primary.withValues(alpha: 0.45)),
      ),
      child: Text(
        'NEW',
        style: AppTypography.caption.copyWith(
          color: AppColors.primary,
          fontWeight: FontWeight.w600,
          letterSpacing: 0.6,
        ),
      ),
    );
  }
}

class _FollowedSeriesCard extends StatelessWidget {
  const _FollowedSeriesCard({
    required this.series,
    required this.onRemove,
    this.actionPending = false,
  });

  final FollowedSeries series;
  final VoidCallback onRemove;
  final bool actionPending;

  @override
  Widget build(BuildContext context) {
    return GlassPanel(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(child: Text(series.title, style: AppTypography.labelLg)),
              _KindBadge(label: series.sourceId),
            ],
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            // chapterCount is 0 until the first successful update check --
            // follow() creates the row without it -- so a freshly followed
            // series would otherwise be labelled "0 chapters", which reads as
            // "this series has none" rather than "not checked yet".
            series.chapterCount > 0
                ? '${series.chapterCount} chapters'
                : 'Not checked yet',
            style: AppTypography.body.copyWith(color: AppColors.muted),
          ),
          Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              TextButton(
                onPressed: actionPending ? null : onRemove,
                style: TextButton.styleFrom(foregroundColor: AppColors.danger),
                child: const Text('Unfollow'),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _KindBadge extends StatelessWidget {
  const _KindBadge({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: AppColors.fg.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(AppRadius.full),
        border: Border.all(color: AppColors.border),
      ),
      child: Text(
        label,
        style: AppTypography.caption.copyWith(color: AppColors.muted),
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
        SkeletonBox(width: 200, height: 44),
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
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.xl3),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, color: AppColors.danger, size: 48),
            const SizedBox(height: AppSpacing.lg),
            Text(
              error.userMessage,
              style: AppTypography.body.copyWith(color: AppColors.muted),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: AppSpacing.xl2),
            PrimaryPillButton(
              label: 'Retry',
              icon: Icons.refresh,
              onPressed: onRetry,
            ),
          ],
        ),
      ),
    );
  }
}
