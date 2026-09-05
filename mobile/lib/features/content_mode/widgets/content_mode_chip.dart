import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/features/content_mode/content_mode.dart';
import 'package:manhwamaniacs/features/content_mode/content_mode_controller.dart';
import 'package:manhwamaniacs/features/content_mode/widgets/content_mode_switch.dart';

/// The active Manga/Novels mode as app-bar chrome: what mode this screen is
/// in, and the way out of it.
///
/// Ten screens are scoped by the mode and only two of them — Library and
/// Sources — could change it, so Downloads or Bookmarks in the wrong mode
/// meant walking back to a tab root to flip a setting the screen never showed.
/// Repeating [ContentModeSwitch] on the other eight is the wrong fix twice
/// over: it is a full-width tray in the content column, and sitting directly
/// above a filter row (Search) or a TabBar (Downloads) a second segmented
/// control reads as "filter this list" rather than "the whole app is in Novels
/// mode".
///
/// So the mode travels as chrome instead, in the shape `ProfileSwitcherChip`
/// already established for the other setting that scopes the entire app: a
/// compact chip in the bar, costing no vertical space, that opens the ONE
/// [ContentModeSwitch] rather than a second implementation of mode selection.
/// Library and Sources keep the inline switch — they are the app's front door
/// and the place novel sources are installed, and a mode a reader never
/// discovers is a mode they never use.
///
/// Renders nothing at all when the novels gate is shut, exactly like the
/// switch it opens.
class ContentModeChip extends ConsumerWidget {
  const ContentModeChip({super.key, this.padding});

  /// Defaults to the inset an [AppBar] action wants. Pass [EdgeInsets.zero]
  /// when mounting it inside a screen's own header row.
  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scope = ref.watch(contentModeScopeProvider);
    if (!scope.showSwitch) return const SizedBox.shrink();

    final colors = context.colors;
    final mode = scope.mode;
    return Padding(
      padding: padding ??
          EdgeInsets.symmetric(
            horizontal: context.space.sm,
            vertical: context.space.xs,
          ),
      child: Semantics(
        button: true,
        label: '${mode.label} mode. Change reading mode',
        child: Material(
          color: colors.surface2.withAlpha(140),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(context.radii.full),
            side: BorderSide(color: colors.border),
          ),
          child: InkWell(
            borderRadius: BorderRadius.circular(context.radii.full),
            onTap: () => showContentModeSheet(context),
            child: Padding(
              padding: EdgeInsets.fromLTRB(
                context.space.md,
                context.space.xs,
                context.space.sm,
                context.space.xs,
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    mode == ContentMode.novel
                        ? Icons.menu_book_rounded
                        : Icons.auto_stories_rounded,
                    size: 16,
                    color: colors.primary,
                  ),
                  SizedBox(width: context.space.xs),
                  Text(mode.label, style: context.text.labelLg),
                  Icon(Icons.expand_more, size: 16, color: colors.muted),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Opens the mode picker: the real [ContentModeSwitch], plus the one sentence
/// that stops it reading as a per-screen filter.
Future<void> showContentModeSheet(BuildContext context) {
  return showModalBottomSheet<void>(
    context: context,
    showDragHandle: true,
    backgroundColor: context.colors.surfaceElevated,
    constraints: const BoxConstraints(maxWidth: 640),
    builder: (_) => const ContentModeSheet(),
  );
}

/// The picker's body. Closes itself the moment a mode is chosen, so the screen
/// underneath is seen re-filtering rather than described as having done so.
class ContentModeSheet extends ConsumerWidget {
  const ContentModeSheet({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.listen<ContentMode>(contentModeControllerProvider, (previous, next) {
      if (previous == next) return;
      final navigator = Navigator.of(context);
      if (navigator.canPop()) navigator.pop();
    });

    return SafeArea(
      top: false,
      child: Padding(
        padding: EdgeInsets.fromLTRB(
          context.space.xl2,
          0,
          context.space.xl2,
          context.space.xl2,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Reading mode', style: context.text.h4),
            SizedBox(height: context.space.xs),
            Text(
              'One setting for the whole app. Your library, sources, search, '
              'downloads and updates all show what you pick here.',
              style: context.text.bodySm
                  .copyWith(color: context.colors.muted, height: 1.4),
            ),
            SizedBox(height: context.space.lg),
            const ContentModeSwitch(),
          ],
        ),
      ),
    );
  }
}
