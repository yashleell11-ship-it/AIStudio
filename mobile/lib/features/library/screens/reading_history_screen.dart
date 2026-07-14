import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/library/models/reading_history_item.dart';
import 'package:manhwamaniacs/features/library/providers/intelligence_providers.dart';
import 'package:manhwamaniacs/shared/widgets/empty_state.dart';
import 'package:manhwamaniacs/shared/widgets/glass_card.dart';
import 'package:manhwamaniacs/shared/widgets/premium/hero_heading.dart';
import 'package:manhwamaniacs/shared/widgets/skeleton_box.dart';

const _weekdays = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

class ReadingHistoryScreen extends ConsumerWidget {
  const ReadingHistoryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final historyAsync = ref.watch(readingHistoryProvider);

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.canPop() ? context.pop() : context.go(Routes.library),
        ),
        title: const Text('Reading History'),
      ),
      body: historyAsync.when(
        loading: () => ListView(
          padding: const EdgeInsets.all(AppSpacing.xl2),
          children: const [
            SkeletonBox(width: double.infinity, height: 180),
            SizedBox(height: AppSpacing.xl2),
            SkeletonBox(width: double.infinity, height: 100),
          ],
        ),
        error: (error, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                error is AppError ? error.userMessage : 'Failed to load reading history.',
                style: AppTypography.body.copyWith(color: AppColors.danger),
              ),
              const SizedBox(height: AppSpacing.lg),
              FilledButton(
                onPressed: () => ref.invalidate(readingHistoryProvider),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
        data: (data) => RefreshIndicator(
          color: AppColors.primary,
          onRefresh: () async => ref.invalidate(readingHistoryProvider),
          child: ListView(
            padding: const EdgeInsets.all(AppSpacing.xl2),
            children: [
              const HeroHeading(text: 'Reading History'),
              const SizedBox(height: AppSpacing.xs),
              Text(
                'Track your reading sessions and activity.',
                style: AppTypography.body.copyWith(color: AppColors.muted),
              ),
              const SizedBox(height: AppSpacing.xl2),
              Text('Last 30 Days', style: AppTypography.h3),
              const SizedBox(height: AppSpacing.md),
              _CalendarGrid(days: data.calendar),
              const SizedBox(height: AppSpacing.xl2),
              Text('Recent Sessions', style: AppTypography.h3),
              const SizedBox(height: AppSpacing.md),
              if (data.sessions.isEmpty)
                const EmptyState(
                  icon: Icons.history,
                  message: 'No reading sessions yet',
                  subtitle: 'Open a chapter from your library to start tracking sessions.',
                )
              else
                ...data.sessions.map(
                  (session) => Padding(
                    padding: const EdgeInsets.only(bottom: AppSpacing.md),
                    child: _SessionCard(session: session),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _CalendarGrid extends StatelessWidget {
  const _CalendarGrid({required this.days});

  final List<ReadingCalendarDay> days;

  @override
  Widget build(BuildContext context) {
    if (days.isEmpty) {
      return Text(
        'No reading activity in the last 30 days.',
        style: AppTypography.body.copyWith(color: AppColors.muted),
      );
    }

    return GlassCard(
      child: Column(
        children: [
          Row(
            children: [
              for (final weekday in _weekdays)
                Expanded(
                  child: Center(
                    child: Text(
                      weekday,
                      style: AppTypography.caption.copyWith(color: AppColors.muted),
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          GridView.builder(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 7,
              mainAxisSpacing: AppSpacing.xs,
              crossAxisSpacing: AppSpacing.xs,
              childAspectRatio: 0.9,
            ),
            itemCount: days.length,
            itemBuilder: (context, index) {
              final day = days[index];
              final dayLabel = day.day.length >= 10 ? day.day.substring(8) : day.day;
              return Container(
                decoration: BoxDecoration(
                  color: day.hasActivity
                      ? AppColors.primary.withAlpha(26)
                      : AppColors.panel,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(dayLabel, style: AppTypography.caption),
                    Text(
                      '${day.pagesRead}',
                      style: AppTypography.labelLg.copyWith(
                        color: day.hasActivity ? AppColors.primary : AppColors.muted,
                      ),
                    ),
                  ],
                ),
              );
            },
          ),
        ],
      ),
    );
  }
}

class _SessionCard extends StatelessWidget {
  const _SessionCard({required this.session});

  final ReadingHistoryItem session;

  @override
  Widget build(BuildContext context) {
    final started = session.startedAt != null
        ? DateFormat.yMMMd().add_jm().format(session.startedAt!.toLocal())
        : null;

    return GlassCard(
      onTap: () => context.push(RoutePaths.seriesDetail(session.seriesId)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            session.seriesTitle ?? 'Unknown Series',
            style: AppTypography.labelLg,
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            session.chapterTitle ?? 'Unknown Chapter',
            style: AppTypography.body.copyWith(color: AppColors.muted),
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            'Pages ${session.startPage}–${session.endPage} · ${session.pagesRead} pages read',
            style: AppTypography.caption,
          ),
          if (started != null) ...[
            const SizedBox(height: AppSpacing.xs),
            Text(started, style: AppTypography.caption.copyWith(color: AppColors.muted)),
          ],
        ],
      ),
    );
  }
}