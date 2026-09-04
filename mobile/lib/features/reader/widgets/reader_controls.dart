import 'dart:ui' show ImageFilter;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/features/reader/providers/reader_filter_provider.dart';
import 'package:manhwamaniacs/features/reader/providers/reader_ui_provider.dart';
import 'package:manhwamaniacs/features/reader/utils/reader_scrub.dart';
import 'package:manhwamaniacs/features/reader/widgets/immersive_safe_area.dart';
import 'package:manhwamaniacs/features/settings/models/reader_defaults.dart';
import 'package:manhwamaniacs/features/settings/providers/settings_provider.dart';
import 'package:manhwamaniacs/shared/widgets/glass_card.dart';

// Speed label for auto-scroll
String _autoScrollLabel(double speed) {
  if (speed <= readerAutoScrollSlow + 5) return 'Slow';
  if (speed <= readerAutoScrollMedium + 5) return 'Medium';
  return 'Fast';
}

const _controlsAnimMs = 220;

// ── Shared glass surface ──────────────────────────────────────────────────────

/// Blurred, translucent panel used by the reader's top and bottom bars so the
/// overlay stays "almost invisible" over the page while remaining legible.
///
/// Eclipse Warm frosted glass — mirrors the app's bottom nav (blur 18, near-
/// black surface, subtle border) plus a soft warm-amber glow so the reader
/// chrome reads as part of the same warm system.
class _GlassSurface extends StatelessWidget {
  const _GlassSurface({required this.child, this.padding});

  final Widget child;
  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context) {
    final br = BorderRadius.circular(AppRadius.xl);
    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: br,
        boxShadow: [
          BoxShadow(
            color: Colors.black.withAlpha(90),
            blurRadius: 18,
            offset: const Offset(0, 6),
          ),
          // Warm amber halo — the Eclipse Warm accent.
          BoxShadow(
            color: AppColors.primary.withAlpha(20),
            blurRadius: 24,
            spreadRadius: -6,
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: br,
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 18, sigmaY: 18),
          child: DecoratedBox(
            decoration: BoxDecoration(
              color: AppColors.surface.withAlpha(184),
              borderRadius: br,
              border: Border.all(color: AppColors.border),
            ),
            child: Padding(
              padding: padding ?? const EdgeInsets.all(AppSpacing.xs),
              child: child,
            ),
          ),
        ),
      ),
    );
  }
}

/// Wraps a bar in the slide + fade + pointer-gating used for show/hide.
class _AnimatedBar extends StatelessWidget {
  const _AnimatedBar({
    required this.visible,
    required this.slideFrom,
    required this.child,
  });

  final bool visible;
  final Offset slideFrom;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    // Honour the platform "reduce motion" setting — the bars snap instead of
    // sliding when animations are disabled.
    final duration = MediaQuery.disableAnimationsOf(context)
        ? Duration.zero
        : const Duration(milliseconds: _controlsAnimMs);
    return IgnorePointer(
      ignoring: !visible,
      child: AnimatedSlide(
        duration: duration,
        curve: Curves.easeOutCubic,
        offset: visible ? Offset.zero : slideFrom,
        child: AnimatedOpacity(
          duration: duration,
          opacity: visible ? 1 : 0,
          child: child,
        ),
      ),
    );
  }
}

// ── Top bar ───────────────────────────────────────────────────────────────────

/// Minimal top bar: back (top-left, like modern readers), chapter title — which
/// doubles as the way into the series page — and optional bookmark + settings
/// actions.
class ReaderTopBar extends StatelessWidget {
  const ReaderTopBar({
    super.key,
    required this.chapterTitle,
    required this.visible,
    required this.onBack,
    required this.onOpenSeries,
    required this.onSettings,
    this.onBookmark,
  });

  final String chapterTitle;
  final bool visible;
  final VoidCallback onBack;

  /// Opens the series page for the chapter being read.
  final VoidCallback onOpenSeries;
  final VoidCallback onSettings;
  final VoidCallback? onBookmark;

  @override
  Widget build(BuildContext context) {
    return _AnimatedBar(
      visible: visible,
      slideFrom: const Offset(0, -1),
      child: ImmersiveSafeArea(
        bottom: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.md,
            AppSpacing.sm,
            AppSpacing.md,
            0,
          ),
          child: _GlassSurface(
            padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xs),
            child: Row(
              children: [
                IconButton(
                  onPressed: onBack,
                  icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 20),
                  tooltip: 'Back',
                  color: AppColors.fg,
                ),
                Expanded(
                  // The title carries the jump rather than a fourth icon: it is
                  // already where a reader looks to know what they are reading,
                  // it reads as a label instead of yet another unlabelled glyph
                  // in a bar that auto-hides, and it leaves the bookmark/gear
                  // pair uncrowded. The chevron is what marks it a destination.
                  child: Tooltip(
                    message: 'Go to series',
                    child: Material(
                      // _GlassSurface is a DecoratedBox, not a Material, so
                      // without this the ink would splash on the Scaffold
                      // behind the page list and never be seen. Transparent —
                      // it paints the splash and nothing else.
                      type: MaterialType.transparency,
                      child: InkWell(
                        onTap: onOpenSeries,
                        borderRadius: BorderRadius.circular(AppRadius.md),
                        child: Padding(
                          padding: const EdgeInsets.symmetric(
                            horizontal: AppSpacing.sm,
                            vertical: AppSpacing.sm,
                          ),
                          child: Row(
                            children: [
                              Flexible(
                                child: Text(
                                  chapterTitle,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: AppTypography.labelLg.copyWith(
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                              ),
                              const SizedBox(width: AppSpacing.xs),
                              const Icon(
                                Icons.chevron_right_rounded,
                                size: 18,
                                color: AppColors.muted,
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
                if (onBookmark != null)
                  IconButton(
                    onPressed: onBookmark,
                    icon: const Icon(Icons.bookmark_add_outlined, size: 20),
                    tooltip: 'Bookmark',
                    color: AppColors.primary,
                    visualDensity: VisualDensity.compact,
                  ),
                IconButton(
                  onPressed: onSettings,
                  icon: const Icon(Icons.tune_rounded, size: 20),
                  tooltip: 'Reader settings',
                  color: AppColors.primary,
                  visualDensity: VisualDensity.compact,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ── Bottom bar ────────────────────────────────────────────────────────────────

/// Minimal bottom bar: previous/next chapter within thumb reach, the page
/// indicator and a draggable position rail. One-handed by design.
class ReaderBottomBar extends StatefulWidget {
  const ReaderBottomBar({
    super.key,
    required this.visiblePage,
    required this.pageCount,
    required this.direction,
    required this.visible,
    required this.hasPrevious,
    required this.hasNext,
    this.onSeekToPage,
    this.onPreviousChapter,
    this.onNextChapter,
    this.onSettings,
  });

  final int visiblePage;
  final int pageCount;

  /// Reading direction, so a right-to-left chapter runs its rail the same way
  /// it runs its pages: the start of the chapter is on the right.
  final ReadingDirection direction;
  final bool visible;
  final bool hasPrevious;
  final bool hasNext;

  /// Jump the reader to a page. ``null`` leaves the rail read-only.
  final ValueChanged<int>? onSeekToPage;
  final VoidCallback? onPreviousChapter;
  final VoidCallback? onNextChapter;

  /// Opens the reader settings sheet — mirrored here so the gear is reachable
  /// one-handed from the bottom bar as well as the top chrome.
  final VoidCallback? onSettings;

  @override
  State<ReaderBottomBar> createState() => _ReaderBottomBarState();
}

class _ReaderBottomBarState extends State<ReaderBottomBar> {
  /// Where the thumb is being dragged to, which is not the same as where the
  /// reader has landed. The visible page is measured back from the scroll
  /// offset, and letting that tug the thumb mid-drag makes it stick.
  int? _dragPage;

  @override
  Widget build(BuildContext context) {
    final pageCount = widget.pageCount;
    final page = _dragPage ?? widget.visiblePage;
    final seek = widget.onSeekToPage;
    final enabled = seek != null && readerScrubEnabled(pageCount);

    return _AnimatedBar(
      visible: widget.visible,
      slideFrom: const Offset(0, 1),
      child: ImmersiveSafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.md,
            0,
            AppSpacing.md,
            AppSpacing.sm,
          ),
          child: _GlassSurface(
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.xs,
              vertical: AppSpacing.xs,
            ),
            child: Row(
              children: [
                IconButton(
                  onPressed: widget.hasPrevious ? widget.onPreviousChapter : null,
                  icon: const Icon(Icons.skip_previous_rounded),
                  tooltip: 'Previous chapter',
                  color: AppColors.primary,
                  disabledColor: AppColors.muted.withAlpha(70),
                ),
                Expanded(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        'Page ${readerScrubValue(page, pageCount).round()}'
                        ' / $pageCount',
                        style: AppTypography.labelSm.copyWith(
                          color: AppColors.muted,
                        ),
                      ),
                      // A real Slider rather than a hand-rolled drag on a
                      // painted rail: touch slop, drag, tap-to-jump, keyboard
                      // and the screen-reader increment/decrement actions all
                      // come with it.
                      SliderTheme(
                        data: SliderTheme.of(context).copyWith(
                          trackHeight: 3,
                          activeTrackColor: AppColors.primary,
                          inactiveTrackColor: AppColors.fg.withAlpha(26),
                          thumbColor: AppColors.primary,
                          // No tick marks: one per page turns the rail into a
                          // dotted line on a long chapter.
                          activeTickMarkColor: Colors.transparent,
                          inactiveTickMarkColor: Colors.transparent,
                          thumbShape:
                              const RoundSliderThumbShape(enabledThumbRadius: 6),
                          overlayShape:
                              const RoundSliderOverlayShape(overlayRadius: 14),
                        ),
                        child: Directionality(
                          textDirection: widget.direction.reverseScroll
                              ? TextDirection.rtl
                              : TextDirection.ltr,
                          child: Slider(
                            value: readerScrubValue(page, pageCount),
                            min: 1,
                            max: readerScrubMax(pageCount),
                            divisions: readerScrubDivisions(pageCount),
                            semanticFormatterCallback: (value) =>
                                'Page ${readerScrubPage(value, pageCount)}'
                                ' of $pageCount',
                            onChanged: enabled
                                ? (value) {
                                    final target =
                                        readerScrubPage(value, pageCount);
                                    setState(() => _dragPage = target);
                                    seek(target);
                                  }
                                : null,
                            onChangeEnd: (_) => setState(() => _dragPage = null),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                IconButton(
                  onPressed: widget.hasNext ? widget.onNextChapter : null,
                  icon: const Icon(Icons.skip_next_rounded),
                  tooltip: 'Next chapter',
                  color: AppColors.primary,
                  disabledColor: AppColors.muted.withAlpha(70),
                ),
                if (widget.onSettings != null)
                  IconButton(
                    onPressed: widget.onSettings,
                    icon: const Icon(Icons.tune_rounded, size: 20),
                    // Distinct from the top bar's canonical 'Reader settings'
                    // gear so the single settings finder stays unambiguous.
                    tooltip: 'More options',
                    color: AppColors.primary,
                    visualDensity: VisualDensity.compact,
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ── Chapter edge prompts ──────────────────────────────────────────────────────

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
                const Icon(Icons.chevron_left, color: AppColors.primary, size: 18),
                const SizedBox(width: AppSpacing.sm),
              ],
              Text(label, style: AppTypography.labelLg),
              if (direction == EdgeDirection.next) ...[
                const SizedBox(width: AppSpacing.sm),
                const Icon(Icons.chevron_right, color: AppColors.primary, size: 18),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

enum EdgeDirection { previous, next }

// There is deliberately no page-count overlay inside the reading area. It used
// to float over the top of the page whenever the controls were hidden, which
// put a permanent "20 / 20" badge on top of the artwork — the one place a
// reader is looking. The count lives in the bottom bar, next to the rail that
// can act on it.

// ── Reader settings + more sheet ──────────────────────────────────────────────

/// Bottom sheet reachable from the top bar. Surfaces the reader's own settings
/// (direction, fit, refresh rate) plus zoom, chapter navigation and bookmark —
/// so the reader is fully controllable without leaving it.
class ReaderMoreSheet extends ConsumerWidget {
  const ReaderMoreSheet({
    super.key,
    this.onPreviousChapter,
    this.onNextChapter,
    this.onOpenSeries,
    this.onBookmark,
    this.showBookmark = true,
  });

  final VoidCallback? onPreviousChapter;
  final VoidCallback? onNextChapter;

  /// Opens the series page for the chapter being read.
  final VoidCallback? onOpenSeries;
  final VoidCallback? onBookmark;
  final bool showBookmark;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ui = ref.watch(readerUiProvider);
    final ctrl = ref.read(readerUiProvider.notifier);
    final defaults = ref.watch(readerDefaultsProvider);
    final settings = ref.read(readerDefaultsProvider.notifier);
    final filter = ref.watch(readerFilterProvider);
    final filterCtrl = ref.read(readerFilterProvider.notifier);

    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.xl2,
          AppSpacing.lg,
          AppSpacing.xl2,
          AppSpacing.xl2,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Drag handle is provided by showModalBottomSheet(showDragHandle:
            // true) so a swipe-down (or a tap-drag on the handle) dismisses the
            // sheet — no manual grabber needed here.
            // Chapter navigation
            Row(
              children: [
                Expanded(
                  child: _SheetNavButton(
                    label: 'Prev',
                    icon: Icons.chevron_left,
                    enabled: onPreviousChapter != null,
                    onTap: onPreviousChapter == null
                        ? null
                        : () {
                            Navigator.pop(context);
                            onPreviousChapter!();
                          },
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: _SheetNavButton(
                    label: 'Next',
                    icon: Icons.chevron_right,
                    iconTrailing: true,
                    enabled: onNextChapter != null,
                    onTap: onNextChapter == null
                        ? null
                        : () {
                            Navigator.pop(context);
                            onNextChapter!();
                          },
                  ),
                ),
              ],
            ),
            // Mirrors the tappable title in the top bar. That bar auto-hides
            // after a few seconds, so a reader who never discovers the title is
            // tappable would have no way to the series page at all; the sheet is
            // where this reader already keeps everything else it can do, and it
            // stays put until dismissed.
            if (onOpenSeries != null) ...[
              const SizedBox(height: AppSpacing.md),
              SizedBox(
                width: double.infinity,
                child: _SheetNavButton(
                  label: 'Go to series',
                  icon: Icons.menu_book_outlined,
                  enabled: true,
                  onTap: () {
                    Navigator.pop(context);
                    onOpenSeries!();
                  },
                ),
              ),
            ],
            const SizedBox(height: AppSpacing.lg),
            const Divider(height: 1),
            const SizedBox(height: AppSpacing.lg),
            // Reader settings — direction
            Text('Reading direction', style: AppTypography.labelLg),
            const SizedBox(height: AppSpacing.xs),
            SegmentedButton<ReadingDirection>(
              segments: ReadingDirection.values
                  .map((d) => ButtonSegment(value: d, label: Text(d.label)))
                  .toList(),
              selected: {defaults.direction},
              showSelectedIcon: false,
              onSelectionChanged: (s) => settings.setDirection(s.first),
            ),
            const SizedBox(height: AppSpacing.lg),
            Text('Fit mode', style: AppTypography.labelLg),
            const SizedBox(height: AppSpacing.xs),
            SegmentedButton<ReaderFitMode>(
              segments: ReaderFitMode.values
                  .map((f) => ButtonSegment(value: f, label: Text(f.label)))
                  .toList(),
              selected: {defaults.fitMode},
              showSelectedIcon: false,
              onSelectionChanged: (s) => settings.setFitMode(s.first),
            ),
            const SizedBox(height: AppSpacing.lg),
            Text('Refresh rate', style: AppTypography.labelLg),
            const SizedBox(height: AppSpacing.xs),
            Wrap(
              spacing: AppSpacing.sm,
              runSpacing: AppSpacing.xs,
              children: ReaderRefreshRate.values.map((rate) {
                return ChoiceChip(
                  label: Text(rate.label),
                  selected: defaults.refreshRate == rate,
                  onSelected: (_) => settings.setRefreshRate(rate),
                );
              }).toList(),
            ),
            const SizedBox(height: AppSpacing.lg),
            const Divider(height: 1),
            const SizedBox(height: AppSpacing.lg),
            // Display — brightness, warmth, page backdrop
            Text('Brightness', style: AppTypography.labelLg),
            Row(
              children: [
                const Icon(Icons.brightness_low, size: 18, color: AppColors.muted),
                Expanded(
                  child: Slider(
                    value: filter.brightness,
                    min: 0.2,
                    onChanged: filterCtrl.setBrightness,
                  ),
                ),
                const Icon(Icons.brightness_high, size: 18, color: AppColors.muted),
              ],
            ),
            Text('Warmth', style: AppTypography.labelLg),
            Row(
              children: [
                const Icon(Icons.nightlight_round, size: 16, color: AppColors.muted),
                Expanded(
                  child: Slider(
                    value: filter.warmth,
                    onChanged: filterCtrl.setWarmth,
                  ),
                ),
                const Icon(Icons.wb_sunny_outlined, size: 16, color: AppColors.muted),
              ],
            ),
            const SizedBox(height: AppSpacing.xs),
            Text('Page background', style: AppTypography.labelLg),
            const SizedBox(height: AppSpacing.xs),
            Wrap(
              spacing: AppSpacing.sm,
              children: ReaderBackground.values.map((bg) {
                return ChoiceChip(
                  label: Text(bg.label),
                  selected: filter.background == bg,
                  onSelected: (_) => filterCtrl.setBackground(bg),
                );
              }).toList(),
            ),
            const SizedBox(height: AppSpacing.sm),
            Text('Color mode', style: AppTypography.labelLg),
            const SizedBox(height: AppSpacing.xs),
            Wrap(
              spacing: AppSpacing.sm,
              children: ReaderColorMode.values.map((mode) {
                return ChoiceChip(
                  label: Text(mode.label),
                  selected: filter.colorMode == mode,
                  onSelected: (_) => filterCtrl.setColorMode(mode),
                );
              }).toList(),
            ),
            const SizedBox(height: AppSpacing.lg),
            const Divider(height: 1),
            const SizedBox(height: AppSpacing.sm),
            // Zoom controls
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                IconButton(
                  onPressed: ctrl.zoomOut,
                  icon: const Icon(Icons.remove, size: 18),
                  tooltip: 'Zoom out',
                ),
                TextButton.icon(
                  onPressed: ctrl.resetZoom,
                  icon: const Icon(Icons.restart_alt, size: 16),
                  label: Text('${(ui.zoomLevel * 100).round()}%'),
                ),
                IconButton(
                  onPressed: ctrl.zoomIn,
                  icon: const Icon(Icons.add, size: 18),
                  tooltip: 'Zoom in',
                ),
              ],
            ),
            // Auto-scroll
            const SizedBox(height: AppSpacing.sm),
            const Divider(height: 1),
            const SizedBox(height: AppSpacing.sm),
            Row(
              children: [
                const Icon(Icons.play_circle_outline, size: 18, color: AppColors.muted),
                const SizedBox(width: AppSpacing.sm),
                Text('Auto-scroll', style: AppTypography.labelLg),
                const Spacer(),
                Switch(
                  value: ui.autoScrollEnabled,
                  onChanged: (_) => ctrl.toggleAutoScroll(),
                  materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
              ],
            ),
            if (ui.autoScrollEnabled) ...[
              const SizedBox(height: AppSpacing.xs),
              Row(
                children: [
                  Text(
                    'Speed: ${_autoScrollLabel(ui.autoScrollSpeed)}',
                    style: AppTypography.bodySm.copyWith(color: AppColors.muted),
                  ),
                  Expanded(
                    child: Slider(
                      value: ui.autoScrollSpeed,
                      min: readerAutoScrollSlow,
                      max: readerAutoScrollFast,
                      divisions: 2,
                      onChanged: ctrl.setAutoScrollSpeed,
                    ),
                  ),
                ],
              ),
            ],
            // Bookmark
            if (showBookmark && onBookmark != null) ...[
              const SizedBox(height: AppSpacing.sm),
              TextButton.icon(
                onPressed: () {
                  Navigator.pop(context);
                  onBookmark!();
                },
                icon: const Icon(Icons.bookmark_outline, size: 18),
                label: const Text('Save bookmark'),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _SheetNavButton extends StatelessWidget {
  const _SheetNavButton({
    required this.label,
    required this.icon,
    required this.enabled,
    this.onTap,
    this.iconTrailing = false,
  });

  final String label;
  final IconData icon;
  final bool enabled;
  final VoidCallback? onTap;
  final bool iconTrailing;

  @override
  Widget build(BuildContext context) {
    final child = Row(
      mainAxisSize: MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        if (!iconTrailing) Icon(icon, size: 18),
        if (!iconTrailing) const SizedBox(width: AppSpacing.xs),
        Text(label),
        if (iconTrailing) const SizedBox(width: AppSpacing.xs),
        if (iconTrailing) Icon(icon, size: 18),
      ],
    );

    return OutlinedButton(
      onPressed: enabled ? onTap : null,
      style: OutlinedButton.styleFrom(
        foregroundColor: enabled ? AppColors.fg : AppColors.muted.withAlpha(77),
        side: BorderSide(
          color: enabled ? AppColors.border : AppColors.border.withAlpha(77),
        ),
      ),
      child: child,
    );
  }
}
