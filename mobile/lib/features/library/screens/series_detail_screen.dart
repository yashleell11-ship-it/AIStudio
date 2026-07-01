import 'package:aistudio_mobile/app/router/routes.dart';
import 'package:aistudio_mobile/app/theme/app_colors.dart';
import 'package:aistudio_mobile/app/theme/app_spacing.dart';
import 'package:aistudio_mobile/app/theme/app_typography.dart';
import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/features/library/models/chapter.dart';
import 'package:aistudio_mobile/features/library/models/series_detail.dart';
import 'package:aistudio_mobile/features/library/providers/series_detail_provider.dart';
import 'package:aistudio_mobile/features/library/utils/cover_url.dart';
import 'package:aistudio_mobile/features/library/utils/series_display.dart';
import 'package:aistudio_mobile/features/library/widgets/series_detail/series_detail_skeleton.dart';
import 'package:aistudio_mobile/shared/providers/core_providers.dart';
import 'package:aistudio_mobile/shared/providers/repository_providers.dart';
import 'package:aistudio_mobile/shared/widgets/glass_card.dart';
import 'package:aistudio_mobile/shared/widgets/series_cover_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

class SeriesDetailScreen extends ConsumerWidget {
  const SeriesDetailScreen({super.key, required this.seriesId});

  final int seriesId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final seriesAsync = ref.watch(seriesDetailProvider(seriesId));

    return Scaffold(
      body: seriesAsync.when(
        loading: () => const SeriesDetailSkeleton(),
        error: (error, _) => _SeriesDetailError(
          error: error is AppError
              ? error
              : UnknownError(message: error.toString(), cause: error),
          onRetry: () => ref.invalidate(seriesDetailProvider(seriesId)),
        ),
        data: (series) => _SeriesDetailContent(series: series),
      ),
    );
  }
}

class _SeriesDetailContent extends ConsumerStatefulWidget {
  const _SeriesDetailContent({required this.series});

  final SeriesDetail series;

  @override
  ConsumerState<_SeriesDetailContent> createState() =>
      _SeriesDetailContentState();
}

class _SeriesDetailContentState extends ConsumerState<_SeriesDetailContent> {
  late SeriesDetail _series;

  @override
  void initState() {
    super.initState();
    _series = widget.series;
  }

  @override
  void didUpdateWidget(_SeriesDetailContent oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.series.id != oldWidget.series.id ||
        widget.series.updatedAt != oldWidget.series.updatedAt) {
      _series = widget.series;
    }
  }

  Future<void> _toggleFavorite() async {
    final repo = ref.read(libraryRepositoryProvider);
    final result = await repo.toggleFavorite(_series.id);
    if (!mounted) return;
    if (result.isErr) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(result.error.userMessage)),
      );
      return;
    }
    setState(() {
      _series = _series.copyWith(isFavorite: !_series.isFavorite);
    });
  }

  @override
  Widget build(BuildContext context) {
    final baseUrl = ref.watch(apiBaseUrlProvider);
    final coverUrl = seriesCoverUrl(baseUrl, _series.id);
    final progress = _series.readingProgress;
    final continueChapterId = progress?.chapterId ?? _series.firstChapterId;
    final continuePage = progress?.lastPage;
    final canRead = continueChapterId != null;
    final numberFormat = NumberFormat.decimalPattern();

    return CustomScrollView(
      slivers: [
        SliverToBoxAdapter(
          child: Stack(
            children: [
              SizedBox(
                height: 280,
                width: double.infinity,
                child: SeriesCoverImage(
                  url: coverUrl,
                  fit: BoxFit.cover,
                  borderRadius: 0,
                ),
              ),
              Positioned.fill(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [
                        AppColors.bg.withAlpha(153),
                        AppColors.bg.withAlpha(204),
                        AppColors.bg,
                      ],
                    ),
                  ),
                ),
              ),
              Positioned(
                top: MediaQuery.paddingOf(context).top + AppSpacing.sm,
                left: AppSpacing.sm,
                child: IconButton.filledTonal(
                  onPressed: () => context.canPop()
                      ? context.pop()
                      : context.go(Routes.libraryBrowse),
                  icon: const Icon(Icons.arrow_back),
                  style: IconButton.styleFrom(
                    backgroundColor: AppColors.bg.withAlpha(128),
                    foregroundColor: AppColors.fg,
                  ),
                ),
              ),
            ],
          ),
        ),
        SliverPadding(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.xl2,
            0,
            AppSpacing.xl2,
            AppSpacing.xl3,
          ),
          sliver: SliverList(
            delegate: SliverChildListDelegate([
              Transform.translate(
                offset: const Offset(0, -48),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Center(
                      child: SeriesCoverImage(
                        url: coverUrl,
                        width: 180,
                        height: 270,
                        borderRadius: AppRadius.xl,
                      ),
                    ),
                    const SizedBox(height: AppSpacing.xl2),
                    Text(_series.title, style: AppTypography.h1),
                    if (_series.originalTitle != null) ...[
                      const SizedBox(height: AppSpacing.xs),
                      Text(
                        _series.originalTitle!,
                        style: AppTypography.body.copyWith(
                          color: AppColors.muted,
                          fontStyle: FontStyle.italic,
                        ),
                      ),
                    ],
                    const SizedBox(height: AppSpacing.lg),
                    OutlinedButton.icon(
                      onPressed: _toggleFavorite,
                      icon: Icon(
                        _series.isFavorite ? Icons.star : Icons.star_border,
                        color:
                            _series.isFavorite ? AppColors.warning : null,
                      ),
                      label: Text(
                        _series.isFavorite ? 'Favorited' : 'Add Favorite',
                      ),
                      style: OutlinedButton.styleFrom(
                        foregroundColor:
                            _series.isFavorite ? AppColors.warning : AppColors.fg,
                        side: BorderSide(
                          color: _series.isFavorite
                              ? AppColors.warning.withAlpha(77)
                              : AppColors.border,
                        ),
                        backgroundColor: _series.isFavorite
                            ? AppColors.warning.withAlpha(26)
                            : AppColors.fg.withAlpha(13),
                      ),
                    ),
                  ],
                ),
              ),
              if (_series.author != null)
                Text(
                  'by ${_series.author}',
                  style: AppTypography.bodyLg.copyWith(color: AppColors.muted),
                ),
              if (_series.artist != null)
                Text(
                  'Art by ${_series.artist}',
                  style: AppTypography.caption,
                ),
              const SizedBox(height: AppSpacing.lg),
              Wrap(
                spacing: AppSpacing.sm,
                runSpacing: AppSpacing.sm,
                children: [
                  if (_series.readingStatus.isNotEmpty)
                    _InfoChip(
                      label: readingStatusLabel(_series.readingStatus)
                          .toUpperCase(),
                      color: readingStatusColor(_series.readingStatus),
                    ),
                  _InfoChip(label: languageLabel(_series.language)),
                  if (_series.year != null) _InfoChip(label: '${_series.year}'),
                ],
              ),
              const SizedBox(height: AppSpacing.lg),
              Wrap(
                spacing: AppSpacing.lg,
                children: [
                  Text('${_series.chapterCount} chapters', style: AppTypography.body),
                  Text(
                    '${numberFormat.format(_series.pageCount)} pages',
                    style: AppTypography.body,
                  ),
                  if (progress != null)
                    Text(
                      '${progress.progressPct.round()}% read',
                      style: AppTypography.body.copyWith(
                        color: AppColors.cyan400,
                      ),
                    ),
                ],
              ),
              if (canRead) ...[
                const SizedBox(height: AppSpacing.xl2),
                FilledButton.icon(
                  onPressed: () {
                    final path =
                        '${RoutePaths.seriesDetail(_series.id)}/chapters/$continueChapterId/read';
                    final uri = continuePage != null
                        ? '$path?page=$continuePage'
                        : path;
                    context.push(uri);
                  },
                  icon: const Icon(Icons.play_arrow),
                  label: Text(
                    progress != null ? 'Continue Reading' : 'Start Reading',
                  ),
                ),
              ],
              if (_series.tags.isNotEmpty) ...[
                const SizedBox(height: AppSpacing.xl2),
                Wrap(
                  spacing: AppSpacing.sm,
                  runSpacing: AppSpacing.sm,
                  children: _series.tags
                      .map(
                        (tag) => Chip(
                          label: Text(tag.name),
                          backgroundColor: tag.color?.withAlpha(38) ??
                              AppColors.fg.withAlpha(13),
                          side: BorderSide(color: AppColors.border),
                        ),
                      )
                      .toList(),
                ),
              ],
              if (_series.collections.isNotEmpty) ...[
                const SizedBox(height: AppSpacing.md),
                Text.rich(
                  TextSpan(
                    style: AppTypography.body.copyWith(color: AppColors.muted),
                    children: [
                      const TextSpan(text: 'In collections: '),
                      for (var i = 0; i < _series.collections.length; i++) ...[
                        if (i > 0) const TextSpan(text: ', '),
                        TextSpan(
                          text: _series.collections[i].name,
                          style: const TextStyle(color: AppColors.primary),
                        ),
                      ],
                    ],
                  ),
                ),
              ],
              if (_series.description != null &&
                  _series.description!.trim().isNotEmpty) ...[
                const SizedBox(height: AppSpacing.xl2),
                Text(
                  _series.description!,
                  style: AppTypography.body.copyWith(height: 1.6),
                ),
              ],
              const SizedBox(height: AppSpacing.xl3),
              Row(
                children: [
                  const Icon(Icons.menu_book_outlined,
                      size: 16, color: AppColors.cyan400),
                  const SizedBox(width: AppSpacing.sm),
                  Text(
                    'CHAPTERS (${_series.chapters.length})',
                    style: AppTypography.label.copyWith(
                      fontWeight: FontWeight.w600,
                      letterSpacing: 1.2,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.lg),
              if (_series.chapters.isEmpty)
                GlassCard(
                  padding: const EdgeInsets.all(AppSpacing.xl2),
                  child: Text(
                    'No chapters found for this series.',
                    style: AppTypography.body.copyWith(color: AppColors.muted),
                  ),
                )
              else
                GlassCard(
                  child: Column(
                    children: [
                      for (var i = 0; i < _series.chapters.length; i++) ...[
                        if (i > 0)
                          Divider(
                            height: 1,
                            color: AppColors.border.withAlpha(77),
                          ),
                        _ChapterRow(
                          chapter: _series.chapters[i],
                          index: i,
                          isCurrent: progress?.chapterId == _series.chapters[i].id,
                          onTap: () => context.push(
                            '${RoutePaths.seriesDetail(_series.id)}/chapters/${_series.chapters[i].id}/read',
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
            ]),
          ),
        ),
      ],
    );
  }
}

class _InfoChip extends StatelessWidget {
  const _InfoChip({required this.label, this.color});

  final String label;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.xs,
      ),
      decoration: BoxDecoration(
        color: (color ?? AppColors.fg).withAlpha(13),
        borderRadius: BorderRadius.circular(AppRadius.full),
        border: Border.all(color: AppColors.border.withAlpha(128)),
      ),
      child: Text(
        label,
        style: AppTypography.caption.copyWith(
          color: color ?? AppColors.muted,
          fontWeight: FontWeight.w500,
        ),
      ),
    );
  }
}

class _ChapterRow extends StatelessWidget {
  const _ChapterRow({
    required this.chapter,
    required this.index,
    required this.isCurrent,
    required this.onTap,
  });

  final ChapterSummary chapter;
  final int index;
  final bool isCurrent;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final chapterNumber = chapter.number?.round() ?? (index + 1);

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.lg,
            vertical: AppSpacing.md,
          ),
          child: Row(
            children: [
              Container(
                width: 36,
                height: 36,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: AppColors.fg.withAlpha(13),
                  borderRadius: BorderRadius.circular(AppRadius.md),
                ),
                child: Text(
                  '$chapterNumber',
                  style: AppTypography.caption.copyWith(
                    fontFeatures: const [FontFeature.tabularFigures()],
                  ),
                ),
              ),
              const SizedBox(width: AppSpacing.lg),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(chapter.title, style: AppTypography.labelLg),
                    Text(
                      '${chapter.pageCount} pages',
                      style: AppTypography.caption,
                    ),
                  ],
                ),
              ),
              if (isCurrent)
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.sm,
                    vertical: 2,
                  ),
                  decoration: BoxDecoration(
                    color: AppColors.primary.withAlpha(51),
                    borderRadius: BorderRadius.circular(AppRadius.full),
                  ),
                  child: Text(
                    'In progress',
                    style: AppTypography.caption.copyWith(
                      color: AppColors.primary,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                )
              else
                const Icon(Icons.chevron_right, color: AppColors.muted),
            ],
          ),
        ),
      ),
    );
  }
}

class _SeriesDetailError extends StatelessWidget {
  const _SeriesDetailError({
    required this.error,
    required this.onRetry,
  });

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
            Text('Could not load series', style: AppTypography.h3),
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
            const SizedBox(height: AppSpacing.md),
            OutlinedButton(
              onPressed: () => context.canPop()
                  ? context.pop()
                  : context.go(Routes.libraryBrowse),
              child: const Text('Back to library'),
            ),
          ],
        ),
      ),
    );
  }
}
