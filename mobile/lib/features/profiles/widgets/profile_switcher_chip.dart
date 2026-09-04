import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
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
      padding: EdgeInsets.symmetric(
        horizontal: context.space.sm,
        vertical: context.space.xs,
      ),
      child: Material(
        color: context.colors.surface2.withAlpha(140),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(context.radii.full),
          side: BorderSide(color: context.colors.accentAmber.withValues(alpha: 0.28)),
        ),
        child: InkWell(
          borderRadius: BorderRadius.circular(context.radii.full),
          onTap: () => context.push(ProfileRoutes.picker),
          child: Padding(
            padding: EdgeInsets.fromLTRB(
              context.space.xs,
              context.space.xs,
              context.space.sm,
              context.space.xs,
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                ProfileAvatar(avatarKey: active.avatarKey, size: 24),
                SizedBox(width: context.space.xs),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 96),
                  child: Text(
                    active.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: context.text.labelLg,
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
