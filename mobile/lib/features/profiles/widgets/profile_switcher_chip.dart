import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/features/profiles/profile_routes.dart';
import 'package:manhwamaniacs/features/profiles/providers/profiles_providers.dart';
import 'package:manhwamaniacs/features/profiles/widgets/profile_avatar.dart';

/// A compact app-bar chip showing the active profile's avatar + name; tapping
/// it opens the picker to switch profiles without logging out. Renders nothing
/// until a profile is selected. Drop it into any [AppBar.actions] list.
class ProfileSwitcherChip extends ConsumerWidget {
  const ProfileSwitcherChip({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final active = ref.watch(activeProfileProvider);
    if (active == null) return const SizedBox.shrink();

    return Padding(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.sm,
        vertical: AppSpacing.xs,
      ),
      child: Material(
        color: context.colors.surface2.withAlpha(140),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadius.full),
          side: BorderSide(color: context.colors.accentAmber.withValues(alpha: 0.28)),
        ),
        child: InkWell(
          borderRadius: BorderRadius.circular(AppRadius.full),
          onTap: () => context.push(ProfileRoutes.picker),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.xs,
              AppSpacing.xs,
              AppSpacing.sm,
              AppSpacing.xs,
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                ProfileAvatar(avatarKey: active.avatarKey, size: 24),
                const SizedBox(width: AppSpacing.xs),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 96),
                  child: Text(
                    active.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: AppTypography.labelLg,
                  ),
                ),
                Icon(
                  Icons.expand_more,
                  size: 16,
                  color: context.colors.muted,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
