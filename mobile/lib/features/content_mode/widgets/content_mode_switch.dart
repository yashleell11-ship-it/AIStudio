import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/features/content_mode/content_mode.dart';
import 'package:manhwamaniacs/features/content_mode/content_mode_controller.dart';
import 'package:manhwamaniacs/features/settings/providers/settings_provider.dart';

/// The Manga / Novels switch: two pills in a tray.
///
/// The web put this at the top of the sidebar, above the nav groups, because
/// that is where a persistent app-wide selector belongs on a desktop. A phone
/// has no sidebar, and the bottom nav is five tabs of finger-sized targets
/// with no room for a sixth control — so it sits at the top of the two screens
/// the mode most obviously changes the meaning of (Library and Sources). It is
/// still one app-wide setting: flipping it on either screen flips it
/// everywhere.
///
/// Renders **nothing at all** when the novels gate is shut. Not a disabled
/// control, not a greyed pill — nothing, so that a deployment without novels
/// is byte-for-byte the app the owner uses today.
class ContentModeSwitch extends ConsumerWidget {
  const ContentModeSwitch({super.key, this.padding});

  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scope = ref.watch(contentModeScopeProvider);
    if (!scope.showSwitch) return const SizedBox.shrink();

    final colors = context.colors;
    return Padding(
      padding: padding ?? EdgeInsets.zero,
      child: Align(
        alignment: Alignment.centerLeft,
        child: Container(
          padding: const EdgeInsets.all(3),
          decoration: BoxDecoration(
            color: colors.surface2,
            borderRadius: BorderRadius.circular(AppRadius.lg),
            border: Border.all(color: colors.border),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              for (final mode in ContentMode.values)
                _ModePill(
                  mode: mode,
                  selected: scope.mode == mode,
                  onTap: () {
                    if (scope.mode == mode) return;
                    ref.read(hapticsProvider).selection();
                    ref
                        .read(contentModeControllerProvider.notifier)
                        .setMode(mode);
                  },
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ModePill extends StatelessWidget {
  const _ModePill({
    required this.mode,
    required this.selected,
    required this.onTap,
  });

  final ContentMode mode;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    return Semantics(
      button: true,
      selected: selected,
      label: '${mode.label} mode',
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(AppRadius.md),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 160),
          curve: Curves.easeOut,
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.md,
            vertical: AppSpacing.xs + 2,
          ),
          decoration: BoxDecoration(
            color: selected ? colors.primary : Colors.transparent,
            borderRadius: BorderRadius.circular(AppRadius.md),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                mode == ContentMode.novel
                    ? Icons.menu_book_rounded
                    : Icons.auto_stories_rounded,
                size: 16,
                color: selected ? colors.primaryFg : colors.muted,
              ),
              const SizedBox(width: AppSpacing.xs),
              Text(
                mode.label,
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
                  color: selected ? colors.primaryFg : colors.muted,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
