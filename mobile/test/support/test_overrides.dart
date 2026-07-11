import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/auth/models/auth_state.dart';
import 'package:manhwamaniacs/features/auth/models/auth_user.dart';
import 'package:manhwamaniacs/features/auth/providers/auth_controller.dart';
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

const setupCompletedPrefKey = 'settings_setup_completed';

/// Default prefs so tests skip the first-run setup redirect.
Map<String, Object> testPrefsDefaults([Map<String, Object> extra = const {}]) {
  return {
    setupCompletedPrefKey: true,
    ...extra,
  };
}
