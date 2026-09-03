import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/app/app.dart';
import 'package:manhwamaniacs/core/config/env.dart';
import 'package:manhwamaniacs/features/profiles/models/profile.dart';
import 'package:manhwamaniacs/features/profiles/providers/profiles_providers.dart';
import 'package:manhwamaniacs/features/profiles/screens/profile_create_screen.dart';
import 'package:manhwamaniacs/features/settings/providers/app_update_provider.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/test_overrides.dart';

/// A brand-new account: the server call succeeds, it just has no profiles yet
/// — exactly what a just-registered user's first `GET /profiles` returns.
class _EmptyProfilesNotifier extends ProfilesNotifier {
  @override
  Future<List<Profile>> build() async => const [];
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets(
    'a freshly registered, profile-less account lands on profile creation, '
    'not a broken empty shell',
    (tester) async {
      SharedPreferences.setMockInitialValues(testPrefsDefaults());
      final prefs = await SharedPreferences.getInstance();

      final container = ProviderContainer(
        overrides: [
          apiBaseUrlOverride(Env.defaultApiUrl),
          sharedPrefsProvider.overrideWithValue(prefs),
          // Authenticated (as register() leaves the app), but deliberately
          // NOT `activeProfileOverride()` / `profileSessionReadyOverride()` —
          // a fresh account has picked no profile yet, which is exactly the
          // state the router's post-auth gate exists to catch.
          authenticatedAuthOverride(),
          profilesProvider.overrideWith(_EmptyProfilesNotifier.new),
          appUpdateProvider.overrideWith((ref) async => null),
          ...noDownloadsStoreOverrides(),
        ],
      );
      addTearDown(container.dispose);

      await tester.pumpWidget(
        UncontrolledProviderScope(
          container: container,
          child: const ManhwaManiacsApp(),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));

      // The auth + profile gate redirected here on its own — this test never
      // navigates explicitly. Not a broken empty shell: a clear prompt and a
      // way forward, not a blank screen or a crash.
      expect(find.text('Create your first profile'), findsOneWidget);
      final addProfile = find.text('ADD PROFILE');
      expect(addProfile, findsOneWidget);

      await tester.tap(addProfile);
      await tester.pumpAndSettle();

      // Reuses the existing profile-create UI rather than a bespoke onboarding
      // form.
      expect(find.byType(ProfileCreateScreen), findsOneWidget);
      expect(find.text('Add profile'), findsOneWidget);
    },
  );
}
