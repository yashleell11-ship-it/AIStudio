import 'package:aistudio_mobile/app/router/routes.dart';
import 'package:aistudio_mobile/app/theme/app_colors.dart';
import 'package:aistudio_mobile/app/theme/app_spacing.dart';
import 'package:aistudio_mobile/app/theme/app_typography.dart';
import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/features/sources/providers/sources_provider.dart';
import 'package:aistudio_mobile/features/sources/utils/chapter_label.dart';
import 'package:aistudio_mobile/shared/widgets/empty_state.dart';
import 'package:aistudio_mobile/shared/widgets/glass_card.dart';
import 'package:aistudio_mobile/shared/widgets/skeleton_box.dart';
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
