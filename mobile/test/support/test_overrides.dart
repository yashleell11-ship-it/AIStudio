import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/auth/models/auth_state.dart';
import 'package:manhwamaniacs/features/auth/models/auth_user.dart';
import 'package:manhwamaniacs/features/auth/providers/auth_controller.dart';
import 'package:manhwamaniacs/features/profiles/models/mood.dart';
import 'package:manhwamaniacs/features/profiles/models/profile.dart';
import 'package:manhwamaniacs/features/profiles/providers/profiles_providers.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';

/// Overrides [apiBaseUrlProvider] for widget/provider tests.
Override apiBaseUrlOverride(String url) =>
    apiBaseUrlProvider.overrideWith((ref) => url);

final _testUser = AuthUser(
  id: 1,
  username: 'tester',
  isAdmin: true,
  createdAt: DateTime.utc(2024),
);

/// Auth controller pre-seeded to an authenticated session — skips the launch
/// token restore and the network entirely.
class _AuthenticatedTestController extends AuthController {
  @override
  AuthState build() => AuthAuthenticated(_testUser);
}

/// Overrides the auth gate to an authenticated session so widget tests that
/// mount the full app land on the app shell instead of the login screen.
Override authenticatedAuthOverride() =>
    authControllerProvider.overrideWith(_AuthenticatedTestController.new);

/// Active reading profile pre-seeded so the post-auth profile gate lets the
/// full-app widget tests through to the shell instead of the profile picker.
class _SeededActiveProfileNotifier extends ActiveProfileNotifier {
  @override
  ActiveProfile? build() => const ActiveProfile(
        id: 1,
        name: 'Tester',
        avatarKey: null,
        mood: Mood.neutral,
      );
}

/// Overrides the active reading profile to a seeded persona so widget tests
/// that mount the full app pass the profile gate and land on the app shell.
Override activeProfileOverride() =>
    activeProfileProvider.overrideWith(_SeededActiveProfileNotifier.new);

/// Profile session pre-opened so the router's post-auth persona gate lets the
/// full-app widget tests straight through to the shell instead of parking on
/// the profile picker (which only opens once per app session).
class _ReadyProfileSessionNotifier extends ProfileSessionReadyNotifier {
  @override
  bool build() => true;
}

/// Overrides [profileSessionReadyProvider] so widget tests that mount the full
/// app skip the once-per-session profile picker and land on the app shell.
Override profileSessionReadyOverride() =>
    profileSessionReadyProvider.overrideWith(_ReadyProfileSessionNotifier.new);

const setupCompletedPrefKey = 'settings_setup_completed';

/// Default prefs so tests skip the first-run setup redirect.
Map<String, Object> testPrefsDefaults([Map<String, Object> extra = const {}]) {
  return {
    setupCompletedPrefKey: true,
    ...extra,
  };
}
