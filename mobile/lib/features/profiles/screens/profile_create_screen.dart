import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/features/profiles/profile_routes.dart';
import 'package:manhwamaniacs/features/profiles/providers/profiles_providers.dart';
import 'package:manhwamaniacs/features/profiles/widgets/profile_form.dart';

/// Full-screen "Add profile" form (route `/profiles/create`).
class ProfileCreateScreen extends ConsumerWidget {
  const ProfileCreateScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ProfileFormScaffold(
      title: 'Add profile',
      submitLabel: 'Create profile',
      onSubmit: (name, avatarKey, mood) =>
          ref.read(profilesProvider.notifier).create(
                name: name,
                avatarKey: avatarKey,
                mood: mood,
              ),
      onSuccess: () => _leave(context),
    );
  }

  void _leave(BuildContext context) {
    if (context.canPop()) {
      context.pop();
    } else {
      context.go(ProfileRoutes.picker);
    }
  }
}
