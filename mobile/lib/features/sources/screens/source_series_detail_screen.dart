import 'package:aistudio_mobile/app/router/routes.dart';
import 'package:aistudio_mobile/app/theme/app_colors.dart';
import 'package:aistudio_mobile/app/theme/app_spacing.dart';
import 'package:aistudio_mobile/app/theme/app_typography.dart';
import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/features/sources/providers/sources_provider.dart';
import 'package:aistudio_mobile/features/sources/utils/chapter_label.dart';
import 'package:aistudio_mobile/features/updates/models/series_tracker.dart';
import 'package:aistudio_mobile/features/updates/providers/updates_provider.dart';
import 'package:aistudio_mobile/shared/widgets/empty_state.dart';
import 'package:aistudio_mobile/shared/widgets/glass_card.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

class SourceSeriesDetailScreen extends ConsumerWidget {
  const SourceSeriesDetailScreen({
    super.key,
    required this.sourceId,
    required this.seriesId,
  });

  final String sourceId;
  final String seriesId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final detailAsync = ref.watch(
      sourceSeriesDetailProvider((sourceId: sourceId, seriesId: seriesId)),
    );
    // Watch the updates provider so the Follow/Unfollow button reflects the
    // current tracker state. autoDispose + family-safe: this screen is the
    // only consumer when the user is browsing a source series.
    final updatesAsync = ref.watch(updatesProvider);

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.go(RoutePaths.sourceBrowse(sourceId)),
        ),
        title: const Text('Source Series'),
      ),
      body: detailAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                error is AppError ? error.userMessage : 'Failed to load series.',
                style: AppTypography.body.copyWith(color: AppColors.danger),
              ),
              const SizedBox(height: AppSpacing.lg),
              FilledButton(
                onPressed: () => ref.invalidate(
                  sourceSeriesDetailProvider((sourceId: sourceId, seriesId: seriesId)),
                ),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
        data: (data) {
          final series = data.series;
          return ListView(
            padding: const EdgeInsets.all(AppSpacing.xl2),
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(12),
                child: AspectRatio(
                  aspectRatio: 2 / 3,
                  child: Image.network(
                    series.coverUrl,
                    fit: BoxFit.cover,
                    errorBuilder: (_, __, ___) => const ColoredBox(color: AppColors.panel),
                  ),
                ),
              ),
              const SizedBox(height: AppSpacing.xl2),
              Text(series.title, style: AppTypography.displayMd),
              if (series.author != null) ...[
                const SizedBox(height: AppSpacing.xs),
                Text(series.author!, style: AppTypography.body.copyWith(color: AppColors.muted)),
              ],
              if (series.description != null && series.description!.isNotEmpty) ...[
                const SizedBox(height: AppSpacing.lg),
                Text(series.description!, style: AppTypography.body),
              ],
              const SizedBox(height: AppSpacing.lg),
              _FollowButton(
                sourceId: sourceId,
                seriesId: seriesId,
                seriesTitle: series.title,
                updatesAsync: updatesAsync,
              ),
              const SizedBox(height: AppSpacing.xl2),
              Text('Chapters', style: AppTypography.h3),
              const SizedBox(height: AppSpacing.md),
              if (data.chapters.isEmpty)
                const EmptyState(
                  icon: Icons.menu_book_outlined,
                  message: 'No chapters available',
                  subtitle: 'This source did not return any chapters for this series.',
                )
              else
                ...data.chapters.map(
                  (chapter) {
                    final label = chapterLabel(
                      number: chapter.number,
                      title: chapter.title,
                    );
                    return Padding(
                      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                      child: GlassCard(
                        onTap: () => context.go(
                          RoutePaths.sourceReader(
                            sourceId,
                            seriesId,
                            chapter.id,
                          ),
                        ),
                        child: Row(
                          children: [
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(label.primary, style: AppTypography.labelLg),
                                  if (label.secondary != null)
                                    Text(label.secondary!, style: AppTypography.bodySm),
                                  Text(
                                    '${chapter.pageCount} pages',
                                    style: AppTypography.caption.copyWith(color: AppColors.muted),
                                  ),
                                ],
                              ),
                            ),
                            const Icon(Icons.chevron_right),
                          ],
                        ),
                      ),
                    );
                  },
                ),
            ],
          );
        },
      ),
    );
  }
}

/// Follow / Unfollow button for the currently-viewed source series.
///
/// Reads follow state from [updatesAsync] (the shared trackers cache) via
/// [UpdatesNotifier.trackerFor]. The button is disabled while a follow or
/// unfollow action is in flight (`actionPending`) or while the trackers list
/// has not yet loaded (so we never show a stale "Follow" label for a series
/// the user is already following).
class _FollowButton extends ConsumerWidget {
  const _FollowButton({
    required this.sourceId,
    required this.seriesId,
    required this.seriesTitle,
    required this.updatesAsync,
  });

  final String sourceId;
  final String seriesId;
  final String seriesTitle;
  final AsyncValue<UpdatesState> updatesAsync;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = updatesAsync.valueOrNull;
    final loading = updatesAsync.isLoading;
    final actionPending = state?.actionPending ?? false;

    // While the trackers list is loading for the first time we cannot know
    // whether this series is followed, so keep the button disabled to avoid
    // a misleading label.
    final tracker = state == null ? null : _lookup(state);
    final isFollowed = tracker != null;
    final busy = actionPending || (loading && state == null);

    String label;
    if (busy) {
      label = isFollowed ? 'Unfollowing…' : 'Following…';
    } else {
      label = isFollowed ? 'Unfollow' : 'Follow';
    }

    return SizedBox(
      width: double.infinity,
      child: FilledButton.icon(
        onPressed: busy ? null : () => _toggle(ref, isFollowed, tracker?.id),
        icon: isFollowed
            ? const Icon(Icons.notifications_off_outlined)
            : const Icon(Icons.notifications_active_outlined),
        label: Text(label),
      ),
    );
  }

  SeriesTracker? _lookup(UpdatesState state) {
    for (final tracker in state.trackers) {
      if (tracker.trackKind == TrackKind.followed &&
          tracker.source == sourceId &&
          tracker.seriesId == seriesId) {
        return tracker;
      }
    }
    return null;
  }

  Future<void> _toggle(WidgetRef ref, bool isFollowed, int? trackerId) async {
    final notifier = ref.read(updatesProvider.notifier);
    if (isFollowed && trackerId != null) {
      await notifier.deleteTracker(trackerId);
    } else {
      await notifier.followSeries(
        source: sourceId,
        seriesId: seriesId,
        seriesTitle: seriesTitle,
      );
    }
  }
}
