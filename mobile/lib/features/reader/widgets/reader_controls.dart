import 'package:aistudio_mobile/app/theme/app_colors.dart';
import 'package:aistudio_mobile/app/theme/app_radius.dart';
import 'package:aistudio_mobile/app/theme/app_spacing.dart';
import 'package:aistudio_mobile/app/theme/app_typography.dart';
import 'package:aistudio_mobile/shared/widgets/glass_card.dart';
import 'package:flutter/material.dart';

class ChapterEdgePrompt extends StatelessWidget {
  const ChapterEdgePrompt({
    super.key,
    required this.label,
    required this.direction,
    required this.onTap,
  });

  final String label;
  final EdgeDirection direction;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.lg,
        vertical: AppSpacing.xl2,
      ),
      child: Center(
        child: GlassCard(
          onTap: onTap,
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.xl2,
            vertical: AppSpacing.md,
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (direction == EdgeDirection.previous) ...[
                const Icon(Icons.chevron_left, color: AppColors.violet400, size: 18),
                const SizedBox(width: AppSpacing.sm),
              ],
              Text(label, style: AppTypography.labelLg),
              if (direction == EdgeDirection.next) ...[
                const SizedBox(width: AppSpacing.sm),
                const Icon(Icons.chevron_right, color: AppColors.violet400, size: 18),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

enum EdgeDirection { previous, next }

class ReaderControlsBar extends StatelessWidget {
  const ReaderControlsBar({
    super.key,
    required this.chapterTitle,
    required this.scrollProgress,
    required this.visiblePage,
    required this.pageCount,
    required this.zoom,
    required this.visible,
    required this.onZoomIn,
    required this.onZoomOut,
    required this.onZoomReset,
    required this.onBack,
    this.onPreviousChapter,
    this.onNextChapter,
    this.onBookmark,
    this.bookmarkPending = false,
    this.showBookmark = true,
  });

  final String chapterTitle;
  final int scrollProgress;
  final int visiblePage;
  final int pageCount;
  final double zoom;
  final bool visible;
  final VoidCallback onZoomIn;
  final VoidCallback onZoomOut;
  final VoidCallback onZoomReset;
  final VoidCallback onBack;
  final VoidCallback? onPreviousChapter;
  final VoidCallback? onNextChapter;
  final VoidCallback? onBookmark;
  final bool bookmarkPending;
  final bool showBookmark;

  @override
  Widget build(BuildContext context) {
    return AnimatedSlide(
      duration: const Duration(milliseconds: 300),
      curve: Curves.easeOut,
      offset: visible ? Offset.zero : const Offset(0, 1),
      child: AnimatedOpacity(
        duration: const Duration(milliseconds: 300),
        opacity: visible ? 1 : 0,
        child: IgnorePointer(
          ignoring: !visible,
          child: Align(
            alignment: Alignment.bottomCenter,
            child: SafeArea(
              top: false,
              child: Padding(
                padding: const EdgeInsets.all(AppSpacing.lg),
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 768),
                  child: Container(
                    decoration: BoxDecoration(
                      color: AppColors.panel.withAlpha(230),
                      borderRadius: BorderRadius.circular(AppRadius.xl),
                      border: Border.all(color: AppColors.border),
                    ),
                    padding: const EdgeInsets.all(AppSpacing.lg),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Row(
                          children: [
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    chapterTitle,
                                    style: AppTypography.labelLg.copyWith(
                                      fontWeight: FontWeight.w600,
                                    ),
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                  const SizedBox(height: AppSpacing.xs),
                                  Text(
                                    'Page $visiblePage / $pageCount · $scrollProgress%',
                                    style: AppTypography.mono.copyWith(
                                      color: AppColors.muted,
                                      fontSize: 11,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            TextButton(onPressed: onBack, child: const Text('Back')),
                          ],
                        ),
                        const SizedBox(height: AppSpacing.md),
                        ClipRRect(
                          borderRadius: BorderRadius.circular(AppRadius.full),
                          child: LinearProgressIndicator(
                            value: scrollProgress / 100,
                            minHeight: 4,
                            backgroundColor: AppColors.fg.withAlpha(26),
                            valueColor: const AlwaysStoppedAnimation<Color>(
                              AppColors.primary,
                            ),
                          ),
                        ),
                        const SizedBox(height: AppSpacing.lg),
                        Wrap(
                          alignment: WrapAlignment.spaceBetween,
                          crossAxisAlignment: WrapCrossAlignment.center,
                          spacing: AppSpacing.sm,
                          runSpacing: AppSpacing.sm,
                          children: [
                            Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                _NavButton(
                                  label: 'Prev',
                                  icon: Icons.chevron_left,
                                  enabled: onPreviousChapter != null,
                                  onTap: onPreviousChapter,
                                ),
                                _NavButton(
                                  label: 'Next',
                                  icon: Icons.chevron_right,
                                  trailing: true,
                                  enabled: onNextChapter != null,
                                  onTap: onNextChapter,
                                ),
                              ],
                            ),
                            Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                IconButton(
                                  onPressed: onZoomOut,
                                  icon: const Icon(Icons.remove, size: 18),
                                  tooltip: 'Zoom out',
                                ),
                                TextButton.icon(
                                  onPressed: onZoomReset,
                                  icon: const Icon(Icons.restart_alt, size: 16),
                                  label: Text('${(zoom * 100).round()}%'),
                                ),
                                IconButton(
                                  onPressed: onZoomIn,
                                  icon: const Icon(Icons.add, size: 18),
                                  tooltip: 'Zoom in',
                                ),
                                if (showBookmark && onBookmark != null)
                                  TextButton.icon(
                                    onPressed: bookmarkPending ? null : onBookmark,
                                    icon: const Icon(Icons.bookmark_outline, size: 18),
                                    label: const Text('Save'),
                                  ),
                              ],
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _NavButton extends StatelessWidget {
  const _NavButton({
    required this.label,
    required this.icon,
    required this.enabled,
    this.onTap,
    this.trailing = false,
  });

  final String label;
  final IconData icon;
  final bool enabled;
  final VoidCallback? onTap;
  final bool trailing;

  @override
  Widget build(BuildContext context) {
    final child = Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (!trailing) Icon(icon, size: 18),
        if (!trailing) const SizedBox(width: AppSpacing.xs),
        Text(label),
        if (trailing) const SizedBox(width: AppSpacing.xs),
        if (trailing) Icon(icon, size: 18),
      ],
    );

    return TextButton(
      onPressed: enabled ? onTap : null,
      style: TextButton.styleFrom(
        foregroundColor: enabled ? AppColors.muted : AppColors.muted.withAlpha(77),
      ),
      child: child,
    );
  }
}

class ReaderPageIndicator extends StatelessWidget {
  const ReaderPageIndicator({
    super.key,
    required this.visiblePage,
    required this.pageCount,
    required this.visible,
  });

  final int visiblePage;
  final int pageCount;
  final bool visible;

  @override
  Widget build(BuildContext context) {
    return AnimatedOpacity(
      duration: const Duration(milliseconds: 300),
      opacity: visible ? 0 : 1,
      child: IgnorePointer(
        ignoring: visible,
        child: SafeArea(
          child: Align(
            alignment: Alignment.topCenter,
            child: Padding(
              padding: const EdgeInsets.only(top: AppSpacing.lg),
              child: Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.lg,
                  vertical: AppSpacing.sm,
                ),
                decoration: BoxDecoration(
                  color: AppColors.panel.withAlpha(230),
                  borderRadius: BorderRadius.circular(AppRadius.full),
                  border: Border.all(color: AppColors.border),
                ),
                child: Text(
                  '$visiblePage / $pageCount',
                  style: AppTypography.mono.copyWith(
                    color: AppColors.muted,
                    fontSize: 11,
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
