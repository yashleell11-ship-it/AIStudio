import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/features/library/models/followed_series.dart';
import 'package:manhwamaniacs/features/library/utils/cover_url.dart';
import 'package:manhwamaniacs/features/sources/utils/chapter_label.dart';
import 'package:manhwamaniacs/features/updates/models/update_notification.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/widgets/pressable.dart';
import 'package:manhwamaniacs/shared/widgets/series_cover_image.dart';

/// Everything the Library card can say *truthfully* about a followed series
/// without firing a per-series network request.
///
/// [FollowedSeries.chapterCount] is only refreshed by the backend update
/// checker, so a freshly-followed series — or one whose connector is erroring
/// — reports 0 even though the series has hundreds of chapters. Rendering "0
/// chapters" is therefore a lie, and the only way to get a real count on this
/// screen would be one chapter-list request per followed series on every
/// Library open. Instead we surface what the already-loaded updates payload
/// knows: the newest chapter we have ever been notified about, and how many
/// of those notifications are still unread.
class FollowedSeriesMeta {
  const FollowedSeriesMeta({
    required this.unreadCount,
    required this.latestChapterLabel,
  });

  /// Unread new-chapter notifications for this series, counted from the same
  /// notification page the Updates tab renders — so the two always agree.
  final int unreadCount;

  /// Label of the newest chapter we have been notified about ("Chapter 120"),
  /// or null when the series has never produced a notification.
  final String? latestChapterLabel;

  static const FollowedSeriesMeta none =
      FollowedSeriesMeta(unreadCount: 0, latestChapterLabel: null);

  /// Derives the meta for [series] from the loaded [notifications].
  static FollowedSeriesMeta forSeries({
    required FollowedSeries series,
    required List<UpdateNotification> notifications,
  }) {
    var unread = 0;
    UpdateNotification? latest;
    for (final notification in notifications) {
      if (notification.followedSeriesId != series.id) continue;
      if (!notification.isRead) unread++;
      if (latest == null || _isNewer(notification, latest)) {
        latest = notification;
      }
    }
    return FollowedSeriesMeta(
      unreadCount: unread,
      latestChapterLabel: latest == null
          ? null
          : chapterLabel(
              number: latest.chapterNumber,
              title: latest.chapterTitle,
            ).primary,
    );
  }

  /// Newest-first ordering: chapter number when both sides have one, else the
  /// creation timestamp, else insertion id.
  static bool _isNewer(UpdateNotification a, UpdateNotification b) {
    final an = a.chapterNumber;
    final bn = b.chapterNumber;
    if (an != null && bn != null && an != bn) return an > bn;
    final at = a.createdAt;
    final bt = b.createdAt;
    if (at != null && bt != null && at != bt) return at.isAfter(bt);
    return a.id > b.id;
  }
}

/// A cover-first Library grid card for one followed series.
///
/// Matches the sources/search cards: cover, title, and a single muted meta
/// line — which is omitted entirely when nothing true is known, rather than
/// claiming "0 chapters".
class FollowedSeriesCard extends ConsumerWidget {
  const FollowedSeriesCard({
    super.key,
    required this.series,
    required this.meta,
    required this.onTap,
  });

  final FollowedSeries series;
  final FollowedSeriesMeta meta;
  final VoidCallback onTap;

  /// One muted line: the latest chapter we actually know about, else a chapter
  /// count only when the checker has populated one, else nothing at all.
  String? get _subtitle {
    final latest = meta.latestChapterLabel;
    if (latest != null) return 'Latest: $latest';
    final known = series.chapterCount;
    if (known <= 0) return null;
    return known == 1 ? '1 chapter' : '$known chapters';
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final baseUrl = ref.watch(apiBaseUrlProvider);
    final coverUrl = followedSeriesCoverUrl(baseUrl, series);
    final subtitle = _subtitle;

    return Pressable(
      onTap: onTap,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: ClipRRect(
              borderRadius: BorderRadius.circular(AppRadius.xl),
              child: Stack(
                fit: StackFit.expand,
                children: [
                  if (coverUrl == null)
                    ColoredBox(color: context.colors.surface2)
                  else
                    SeriesCoverImage(url: coverUrl, borderRadius: AppRadius.xl),
                  if (meta.unreadCount > 0)
                    Positioned(
                      top: AppSpacing.sm,
                      right: AppSpacing.sm,
                      child: _NewBadge(count: meta.unreadCount),
                    ),
                ],
              ),
            ),
          ),
          const SizedBox(height: AppSpacing.sm),
          Text(
            series.title,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: AppTypography.label.copyWith(
              color: context.colors.fg,
              height: 1.25,
              fontWeight: FontWeight.w600,
            ),
          ),
          if (subtitle != null) ...[
            const SizedBox(height: AppSpacing.xxs),
            Text(
              subtitle,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: AppTypography.caption.copyWith(color: context.colors.muted),
            ),
          ],
        ],
      ),
    );
  }
}

/// Warm amber "N NEW" pill for unread new-chapter notifications.
class _NewBadge extends StatelessWidget {
  const _NewBadge({required this.count});

  final int count;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.sm,
        vertical: AppSpacing.xxs,
      ),
      decoration: BoxDecoration(
        color: context.colors.primary,
        borderRadius: BorderRadius.circular(AppRadius.pill),
      ),
      child: Text(
        '$count NEW',
        style: AppTypography.caption.copyWith(
          color: context.colors.primaryFg,
          fontSize: 10,
          fontWeight: FontWeight.w700,
          letterSpacing: 0.6,
        ),
      ),
    );
  }
}
