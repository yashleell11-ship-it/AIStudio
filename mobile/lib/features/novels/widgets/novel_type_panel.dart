import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/features/novels/models/novel_palette.dart';
import 'package:manhwamaniacs/features/novels/models/novel_typography.dart';
import 'package:manhwamaniacs/features/novels/providers/novel_preferences_provider.dart';
import 'package:manhwamaniacs/features/novels/widgets/novel_chapter_view.dart';

/// Type and surface controls, as a sheet painted in the reading palette.
///
/// Painted in the palette, not the app theme, on purpose: the whole point of
/// the palette picker is judging colours against the page, and a picker that
/// arrives on an obsidian app sheet makes every warm surface look wrong. It
/// also means the sheet is legible on Paper in daylight, which an app-themed
/// dark sheet is not.
///
/// Size / leading / measure / face persist per SERIES; the palette persists
/// per PROFILE. That split is the one the manga reader already draws between
/// its per-series display mode and its app-wide dimmer — a book's type is a
/// property of the book, and the surface is a property of the room.
class NovelTypePanel extends ConsumerWidget {
  const NovelTypePanel({
    super.key,
    required this.seriesPrefsKey,
    required this.surface,
  });

  final String seriesPrefsKey;
  final NovelSurfaceColors surface;

  static Future<void> show(
    BuildContext context, {
    required String seriesPrefsKey,
    required NovelSurfaceColors surface,
  }) {
    return showModalBottomSheet<void>(
      context: context,
      backgroundColor: surface.bg,
      barrierColor: Colors.black.withValues(alpha: 0.4),
      isScrollControlled: true,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(context.radii.xl)),
      ),
      builder: (context) => NovelTypePanel(
        seriesPrefsKey: seriesPrefsKey,
        surface: surface,
      ),
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final prefs = ref.watch(novelPreferencesControllerProvider(seriesPrefsKey));
    final controller =
        ref.read(novelPreferencesControllerProvider(seriesPrefsKey).notifier);
    final storedPalette = ref.watch(novelPaletteControllerProvider);
    final choice = NovelPalettes.resolveChoice(
      storedPalette,
      appIsDark: Theme.of(context).brightness == Brightness.dark,
    );

    return SafeArea(
      top: false,
      child: SingleChildScrollView(
        padding: EdgeInsets.fromLTRB(
          context.space.lg,
          context.space.md,
          context.space.lg,
          context.space.lg,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            Center(
              child: Container(
                width: 36,
                height: 4,
                decoration: BoxDecoration(
                  color: surface.rule,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
            SizedBox(height: context.space.lg),
            _FaceToggle(
              value: prefs.fontFamily,
              surface: surface,
              onChanged: controller.setFontFamily,
            ),
            SizedBox(height: context.space.lg),
            _Stepper(
              label: 'Text size',
              value: '${prefs.fontSize.round()}',
              surface: surface,
              onLess: prefs.fontSize > kMinNovelFontSize
                  ? () => controller.setFontSize(
                        stepNovelFontSize(prefs.fontSize, -1),
                      )
                  : null,
              onMore: prefs.fontSize < kMaxNovelFontSize
                  ? () => controller.setFontSize(
                        stepNovelFontSize(prefs.fontSize, 1),
                      )
                  : null,
            ),
            _Stepper(
              label: 'Line spacing',
              value: prefs.lineHeight.toStringAsFixed(2),
              surface: surface,
              onLess: prefs.lineHeight > kMinNovelLineHeight
                  ? () => controller.setLineHeight(
                        stepNovelLineHeight(prefs.lineHeight, -1),
                      )
                  : null,
              onMore: prefs.lineHeight < kMaxNovelLineHeight
                  ? () => controller.setLineHeight(
                        stepNovelLineHeight(prefs.lineHeight, 1),
                      )
                  : null,
            ),
            _Stepper(
              label: 'Line width',
              value: '${prefs.measure.round()} ch',
              surface: surface,
              onLess: prefs.measure > kMinNovelMeasure
                  ? () => controller.setMeasure(
                        stepNovelMeasure(prefs.measure, -1),
                      )
                  : null,
              onMore: prefs.measure < kMaxNovelMeasure
                  ? () => controller.setMeasure(
                        stepNovelMeasure(prefs.measure, 1),
                      )
                  : null,
            ),
            SizedBox(height: context.space.lg),
            _SectionLabel('Page', surface: surface),
            SizedBox(height: context.space.sm),
            _PaletteGrid(
              choice: choice,
              surface: surface,
              onPick: (id) =>
                  ref.read(novelPaletteControllerProvider.notifier).setChoice(id),
            ),
          ],
        ),
      ),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel(this.text, {required this.surface});

  final String text;
  final NovelSurfaceColors surface;

  @override
  Widget build(BuildContext context) => Text(
        text.toUpperCase(),
        style: TextStyle(
          fontSize: 11,
          letterSpacing: 1.2,
          fontWeight: FontWeight.w700,
          color: surface.muted,
        ),
      );
}

class _FaceToggle extends StatelessWidget {
  const _FaceToggle({
    required this.value,
    required this.surface,
    required this.onChanged,
  });

  final NovelFontFamily value;
  final NovelSurfaceColors surface;
  final ValueChanged<NovelFontFamily> onChanged;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        for (final family in NovelFontFamily.values)
          Expanded(
            child: Padding(
              padding: EdgeInsets.only(
                right: family == NovelFontFamily.serif ? context.space.sm : 0,
              ),
              child: InkWell(
                onTap: () => onChanged(family),
                borderRadius: BorderRadius.circular(context.radii.md),
                child: Container(
                  padding: EdgeInsets.symmetric(vertical: context.space.md),
                  decoration: BoxDecoration(
                    color: value == family
                        ? surface.ink.withValues(alpha: 0.10)
                        : Colors.transparent,
                    borderRadius: BorderRadius.circular(context.radii.md),
                    border: Border.all(
                      color: value == family ? surface.ink : surface.rule,
                    ),
                  ),
                  child: Center(
                    // Set in the face it selects — the only honest preview.
                    child: Text(
                      family == NovelFontFamily.serif ? 'Serif' : 'Sans',
                      style: TextStyle(
                        fontFamily: novelFontStack(family).first,
                        fontFamilyFallback: novelFontStack(family).sublist(1),
                        fontSize: 16,
                        color: surface.ink,
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }
}

class _Stepper extends StatelessWidget {
  const _Stepper({
    required this.label,
    required this.value,
    required this.surface,
    required this.onLess,
    required this.onMore,
  });

  final String label;
  final String value;
  final NovelSurfaceColors surface;
  final VoidCallback? onLess;
  final VoidCallback? onMore;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.symmetric(vertical: context.space.xs),
      child: Row(
        children: [
          Expanded(
            child: Text(
              label,
              style: TextStyle(fontSize: 15, color: surface.ink),
            ),
          ),
          Text(
            value,
            style: TextStyle(
              fontSize: 13,
              color: surface.muted,
              fontFeatures: const [FontFeature.tabularFigures()],
            ),
          ),
          SizedBox(width: context.space.sm),
          _RoundButton(icon: Icons.remove, surface: surface, onTap: onLess),
          SizedBox(width: context.space.xs),
          _RoundButton(icon: Icons.add, surface: surface, onTap: onMore),
        ],
      ),
    );
  }
}

class _RoundButton extends StatelessWidget {
  const _RoundButton({
    required this.icon,
    required this.surface,
    required this.onTap,
  });

  final IconData icon;
  final NovelSurfaceColors surface;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final enabled = onTap != null;
    return InkWell(
      onTap: onTap,
      customBorder: const CircleBorder(),
      child: Container(
        width: 36,
        height: 36,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          border: Border.all(color: surface.rule),
        ),
        child: Icon(
          icon,
          size: 18,
          color: enabled ? surface.ink : surface.muted.withValues(alpha: 0.4),
        ),
      ),
    );
  }
}

/// Every surface as a swatch of itself: the background painted, the label set
/// in that palette's own ink. A list of names would tell the reader nothing.
class _PaletteGrid extends StatelessWidget {
  const _PaletteGrid({
    required this.choice,
    required this.surface,
    required this.onPick,
  });

  final String choice;
  final NovelSurfaceColors surface;
  final ValueChanged<String> onPick;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: context.space.sm,
      runSpacing: context.space.sm,
      children: [
        for (final palette in NovelPalettes.all)
          _Swatch(
            label: palette.label,
            bg: palette.bg,
            ink: palette.ink,
            selected: choice == palette.id,
            outline: surface.rule,
            selectedOutline: surface.ink,
            onTap: () => onPick(palette.id),
          ),
        _Swatch(
          label: 'App theme',
          bg: Theme.of(context).scaffoldBackgroundColor,
          ink: DefaultTextStyle.of(context).style.color ?? surface.ink,
          selected: choice == NovelPalettes.followAppId,
          outline: surface.rule,
          selectedOutline: surface.ink,
          onTap: () => onPick(NovelPalettes.followAppId),
        ),
      ],
    );
  }
}

class _Swatch extends StatelessWidget {
  const _Swatch({
    required this.label,
    required this.bg,
    required this.ink,
    required this.selected,
    required this.outline,
    required this.selectedOutline,
    required this.onTap,
  });

  final String label;
  final Color bg;
  final Color ink;
  final bool selected;
  final Color outline;
  final Color selectedOutline;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      selected: selected,
      label: label,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(context.radii.md),
        child: Container(
          padding: EdgeInsets.symmetric(
            horizontal: context.space.md,
            vertical: context.space.sm,
          ),
          decoration: BoxDecoration(
            color: bg,
            borderRadius: BorderRadius.circular(context.radii.md),
            border: Border.all(
              color: selected ? selectedOutline : outline,
              width: selected ? 2 : 1,
            ),
          ),
          child: Text(
            label,
            style: TextStyle(
              fontSize: 13,
              color: ink,
              fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
            ),
          ),
        ),
      ),
    );
  }
}
