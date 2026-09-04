import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/content_mode/content_mode.dart';
import 'package:manhwamaniacs/features/content_mode/content_mode_controller.dart';
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
    final scope = ref.watch(contentModeScopeProvider);

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
          padding: EdgeInsets.all(context.space.xl2),
          children: [
            const SkeletonBox(width: double.infinity, height: 100),
            SizedBox(height: context.space.md),
            const SkeletonBox(width: double.infinity, height: 100),
          ],
        ),
        error: (error, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                error is AppError ? error.userMessage : 'Failed to load reading history.',
                style: context.text.body.copyWith(color: context.colors.danger),
              ),
              SizedBox(height: context.space.lg),
              FilledButton(
                onPressed: () => ref.invalidate(readingHistoryProvider),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
        data: (allSessions) {
          final sessions = scope.filter(allSessions, (s) => s.sourceId);
          return RefreshIndicator(
          color: context.colors.primary,
          onRefresh: () async => ref.invalidate(readingHistoryProvider),
          child: ListView(
            padding: EdgeInsets.all(context.space.xl2),
            children: [
              const HeroHeading(text: 'Reading History'),
              SizedBox(height: context.space.xs),
              Text(
                'Your most recently read chapters.',
                style: context.text.body.copyWith(color: context.colors.muted),
              ),
              SizedBox(height: context.space.xl2),
              if (sessions.isEmpty)
                const EmptyState(
                  icon: Icons.history,
                  message: 'No reading history yet',
                  subtitle: 'Open a chapter from your library to start tracking history.',
                )
              else
                ...sessions.map(
                  (session) => Padding(
                    padding: EdgeInsets.only(bottom: context.space.md),
                    child: _SessionCard(
                      session: session,
                      isNovel: scope.modeOf(session.sourceId) ==
                          ContentMode.novel,
                    ),
                  ),
                ),
            ],
          ),
          );
        },
      ),
    );
  }
}

class _SessionCard extends StatelessWidget {
  const _SessionCard({required this.session, required this.isNovel});

  final ReadingHistoryItem session;

  /// Which reader this row opens. History rows carry a source id and no kind,
  /// so the kind comes from the source-mode index.
  final bool isNovel;

  @override
  Widget build(BuildContext context) {
    final lastRead = session.lastReadAt != null
        ? DateFormat.yMMMd().add_jm().format(session.lastReadAt!.toLocal())
        : null;
    final label = chapterLabel(number: session.chapterNumber, title: null);

    return GlassCard(
      onTap: () => context.push(
        isNovel
            ? RoutePaths.novelReader(
                session.sourceId,
                session.seriesKey,
                session.chapterKey,
              )
            : RoutePaths.reader(
                session.sourceId,
                session.seriesKey,
                session.chapterKey,
              ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label.primary, style: context.text.labelLg),
          SizedBox(height: context.space.xs),
          Text(
            session.sourceId,
            style: context.text.body.copyWith(color: context.colors.muted),
          ),
          SizedBox(height: context.space.xs),
          Text(
            session.isCompleted
                ? '${session.pageCount}/${session.pageCount} pages'
                : 'Page ${session.lastPage}${session.pageCount > 0 ? '/${session.pageCount}' : ''}',
            style: context.text.caption.copyWith(color: context.colors.muted),
          ),
          if (lastRead != null) ...[
            SizedBox(height: context.space.xs),
            Text(lastRead, style: context.text.caption.copyWith(color: context.colors.muted)),
          ],
        ],
      ),
    );
  }
}
