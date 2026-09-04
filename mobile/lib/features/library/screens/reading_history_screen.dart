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
import 'package:manhwamaniacs/features/sources/utils/chapter_label.dart';
import 'package:manhwamaniacs/shared/widgets/empty_state.dart';
import 'package:manhwamaniacs/shared/widgets/glass_card.dart';
import 'package:manhwamaniacs/shared/widgets/premium/hero_heading.dart';
import 'package:manhwamaniacs/shared/widgets/skeleton_box.dart';

/// Reading history — source-native (`GET /reader/history`). Rows are stored
/// reading-position rows, not sessions: no titles, no start/end page range,
/// no calendar (all removed with the local catalog and reading_sessions
/// aggregation the old backend built those from).
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
            SkeletonBox(width: double.infinity, height: 100),
            SizedBox(height: AppSpacing.md),
            SkeletonBox(width: double.infinity, height: 100),
          ],
        ),
        error: (error, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                error is AppError ? error.userMessage : 'Failed to load reading history.',
                style: AppTypography.body.copyWith(color: context.colors.danger),
              ),
              const SizedBox(height: AppSpacing.lg),
              FilledButton(
                onPressed: () => ref.invalidate(readingHistoryProvider),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
        data: (sessions) => RefreshIndicator(
          color: context.colors.primary,
          onRefresh: () async => ref.invalidate(readingHistoryProvider),
          child: ListView(
            padding: const EdgeInsets.all(AppSpacing.xl2),
            children: [
              const HeroHeading(text: 'Reading History'),
              const SizedBox(height: AppSpacing.xs),
              Text(
                'Your most recently read chapters.',
                style: AppTypography.body.copyWith(color: context.colors.muted),
              ),
              const SizedBox(height: AppSpacing.xl2),
              if (sessions.isEmpty)
                const EmptyState(
                  icon: Icons.history,
                  message: 'No reading history yet',
                  subtitle: 'Open a chapter from your library to start tracking history.',
                )
              else
                ...sessions.map(
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

class _SessionCard extends StatelessWidget {
  const _SessionCard({required this.session});

  final ReadingHistoryItem session;

  @override
  Widget build(BuildContext context) {
    final lastRead = session.lastReadAt != null
        ? DateFormat.yMMMd().add_jm().format(session.lastReadAt!.toLocal())
        : null;
    final label = chapterLabel(number: session.chapterNumber, title: null);

    return GlassCard(
      onTap: () => context.push(
        RoutePaths.reader(session.sourceId, session.seriesKey, session.chapterKey),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label.primary, style: AppTypography.labelLg),
          const SizedBox(height: AppSpacing.xs),
          Text(
            session.sourceId,
            style: AppTypography.body.copyWith(color: context.colors.muted),
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            session.isCompleted
                ? '${session.pageCount}/${session.pageCount} pages'
                : 'Page ${session.lastPage}${session.pageCount > 0 ? '/${session.pageCount}' : ''}',
            style: AppTypography.caption.copyWith(color: context.colors.muted),
          ),
          if (lastRead != null) ...[
            const SizedBox(height: AppSpacing.xs),
            Text(lastRead, style: AppTypography.caption.copyWith(color: context.colors.muted)),
          ],
        ],
      ),
    );
  }
}
