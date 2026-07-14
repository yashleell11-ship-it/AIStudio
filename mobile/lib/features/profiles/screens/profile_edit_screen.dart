import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/features/profiles/models/profile.dart';
import 'package:manhwamaniacs/features/profiles/models/profile_avatar.dart';
import 'package:manhwamaniacs/features/profiles/profile_routes.dart';
import 'package:manhwamaniacs/features/profiles/providers/profiles_providers.dart';
import 'package:manhwamaniacs/features/profiles/widgets/profile_form.dart';
import 'package:manhwamaniacs/shared/widgets/empty_state.dart';

/// Full-screen "Edit profile" form (route `/profiles/edit/:id`). Reads the
/// profile from the shared list; falls back to a not-found state if the id no
/// longer resolves (e.g. deleted on another device).
class ProfileEditScreen extends ConsumerWidget {
  const ProfileEditScreen({super.key, required this.profileId});

  final int profileId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final profilesAsync = ref.watch(profilesProvider);

    return profilesAsync.when(
      loading: () => const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      ),
      error: (error, _) => Scaffold(
        appBar: AppBar(title: const Text('Edit profile')),
        body: Padding(
          padding: const EdgeInsets.all(AppSpacing.xl2),
          child: EmptyState(
            icon: Icons.error_outline,
            message: "Couldn't load profile",
            subtitle: error.toString(),
          ),
        ),
      ),
      data: (profiles) {
        final profile = _findProfile(profiles);
        if (profile == null) {
          return Scaffold(
            appBar: AppBar(title: const Text('Edit profile')),
            body: const Padding(
              padding: EdgeInsets.all(AppSpacing.xl2),
              child: EmptyState(
                icon: Icons.person_off_outlined,
                message: 'Profile not found',
                subtitle: 'This profile may have been removed.',
              ),
            ),
          );
        }
        return ProfileFormScaffold(
          title: 'Edit profile',
          submitLabel: 'Save changes',
          initialName: profile.name,
          initialAvatarKey: profile.avatarKey ?? kDefaultAvatarKey,
          initialMood: profile.mood,
          onSubmit: (name, avatarKey, mood) =>
              ref.read(profilesProvider.notifier).edit(
                    profile.id,
                    name: name,
                    avatarKey: avatarKey,
                    mood: mood,
                  ),
          onDelete: () =>
              ref.read(profilesProvider.notifier).delete(profile.id),
          onSuccess: () => _leave(context),
        );
      },
    );
  }

  Profile? _findProfile(List<Profile> profiles) {
    for (final profile in profiles) {
      if (profile.id == profileId) return profile;
    }
    return null;
  }

  void _leave(BuildContext context) {
    if (context.canPop()) {
      context.pop();
    } else {
      context.go(ProfileRoutes.picker);
    }
  }
}
