import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/profiles/models/mood.dart';
import 'package:manhwamaniacs/features/profiles/models/profile.dart';
import 'package:manhwamaniacs/features/profiles/profile_animations.dart';
import 'package:manhwamaniacs/features/profiles/profile_routes.dart';
import 'package:manhwamaniacs/features/profiles/providers/profiles_providers.dart';
import 'package:manhwamaniacs/features/profiles/screens/profile_picker_screen.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

Profile _profile(int id, String name, Mood mood) => Profile(
      id: id,
      name: name,
      avatarKey: 'violet',
      mood: mood,
      sortOrder: id,
      matureContentEnabled: false,
      createdAt: DateTime.utc(2024),
    );

/// Serves a fixed profile list without touching the network.
class _StubProfilesNotifier extends ProfilesNotifier {
  _StubProfilesNotifier(this._items);
  final List<Profile> _items;

  @override
  Future<List<Profile>> build() async => _items;
}

/// Fails the way an unreachable server does — the list is server data, so with
/// the NAS down this is all the picker ever gets.
class _UnreachableProfilesNotifier extends ProfilesNotifier {
  @override
  Future<List<Profile>> build() async =>
      throw const NetworkError(message: 'blackholed', host: 'nas.local');
}

/// The snapshot a previous session left on this device.
const _persistedActiveProfile = {
  'mm.active_profile':
      '{"id":1,"name":"Alex","avatar_key":"violet","mood":"romantic"}',
};

Finder get _takeover => find.byKey(const Key('profile-mood-takeover'));

Future<void> _pumpPicker(
  WidgetTester tester,
  List<Profile> profiles, {
  bool reduceMotion = true,
}) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        sharedPrefsProvider.overrideWithValue(prefs),
        profilesProvider.overrideWith(() => _StubProfilesNotifier(profiles)),
      ],
      child: MaterialApp(
        // disableAnimations skips the ScrollReveal entrance so tiles are
        // present immediately (reduced-motion path).
        home: MediaQuery(
          data: MediaQueryData(disableAnimations: reduceMotion),
          child: const ProfilePickerScreen(),
        ),
      ),
    ),
  );
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 100));
}

/// Pumps the picker inside a real [GoRouter] so a selection can navigate home.
/// Returns nothing; assert on `find.text('HOME')` for the landing route.
Future<void> _pumpRoutedPicker(
  WidgetTester tester,
  List<Profile> profiles, {
  required bool reduceMotion,
  Map<String, Object> prefsValues = const {},
  Override? profilesOverride,
}) async {
  SharedPreferences.setMockInitialValues(prefsValues);
  final prefs = await SharedPreferences.getInstance();
  final router = GoRouter(
    initialLocation: ProfileRoutes.picker,
    routes: [
      GoRoute(
        path: ProfileRoutes.picker,
        builder: (context, state) => const ProfilePickerScreen(),
      ),
      GoRoute(
        path: Routes.home,
        builder: (context, state) => const Scaffold(body: Text('HOME')),
      ),
    ],
  );
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        sharedPrefsProvider.overrideWithValue(prefs),
        profilesOverride ??
            profilesProvider.overrideWith(() => _StubProfilesNotifier(profiles)),
      ],
      child: MaterialApp.router(
        routerConfig: router,
        builder: (context, child) => MediaQuery(
          data: MediaQueryData(disableAnimations: reduceMotion),
          child: child ?? const SizedBox.shrink(),
        ),
      ),
    ),
  );
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 100));
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('shows the prompt, profiles and the add tile', (tester) async {
    await _pumpPicker(tester, [
      _profile(1, 'Alex', Mood.romantic),
      _profile(2, 'Sam', Mood.action),
    ]);

    expect(find.text('What are you going to read today?'), findsOneWidget);
    expect(find.text('Alex'), findsOneWidget);
    expect(find.text('Sam'), findsOneWidget);
    expect(find.text('Add profile'), findsOneWidget);
  });

  testWidgets('hides the add tile once the max is reached', (tester) async {
    await _pumpPicker(tester, [
      for (var i = 0; i < kMaxProfiles; i++)
        _profile(i + 1, 'Reader $i', Mood.neutral),
    ]);

    expect(find.text('Add profile'), findsNothing);
  });

  testWidgets('Manage toggle switches the helper copy', (tester) async {
    await _pumpPicker(tester, [_profile(1, 'Alex', Mood.romantic)]);

    expect(find.text('Choose a profile to continue.'), findsOneWidget);
    await tester.tap(find.text('Manage'));
    await tester.pump();

    expect(find.text('Tap a profile to edit it.'), findsOneWidget);
    expect(find.text('Done'), findsOneWidget);
  });

  testWidgets('empty state prompts creating the first profile', (tester) async {
    await _pumpPicker(tester, const []);

    expect(find.text('Create your first profile'), findsOneWidget);
    // The empty-state CTA is a PrimaryPillButton, which uppercases its label.
    expect(find.text('ADD PROFILE'), findsOneWidget);
  });

  testWidgets('reduced motion selects instantly and navigates home',
      (tester) async {
    await _pumpRoutedPicker(
      tester,
      [_profile(1, 'Alex', Mood.romantic)],
      reduceMotion: true,
    );

    expect(find.text('HOME'), findsNothing);
    await tester.tap(find.text('Alex'));
    // No 5s ceremony: a couple of pumps to let the async commit resolve.
    await tester.pump();
    await tester.pump();

    expect(find.text('HOME'), findsOneWidget);
    // Once the route transition settles the picker (and its takeover) is gone —
    // and it got there without the multi-second ceremony.
    await tester.pumpAndSettle();
    expect(_takeover, findsNothing);
  });

  testWidgets('normal motion floods full-screen before landing home',
      (tester) async {
    await _pumpRoutedPicker(
      tester,
      [
        _profile(1, 'Alex', Mood.romantic),
        _profile(2, 'Sam', Mood.action),
      ],
      reduceMotion: false,
    );

    await tester.tap(find.text('Alex'));
    await tester.pump();

    // Mid-ceremony: the takeover covers the screen and we have NOT navigated.
    await tester.pump(const Duration(milliseconds: 800));
    expect(_takeover, findsOneWidget);
    expect(find.text('HOME'), findsNothing);

    // Deep into the identity phase the chosen name is mirrored at centre (so it
    // appears on both its tile and the takeover).
    await tester.pump(const Duration(milliseconds: 1800));
    expect(find.text('Alex'), findsNWidgets(2));

    // Let the ~5s ceremony finish; the commit then routes into home.
    await tester.pumpAndSettle();
    expect(find.text('HOME'), findsOneWidget);
    expect(_takeover, findsNothing);
  });

  testWidgets('an unreachable server offers the persisted profile and a retry',
      (tester) async {
    await _pumpRoutedPicker(
      tester,
      const [],
      reduceMotion: true,
      prefsValues: _persistedActiveProfile,
      profilesOverride:
          profilesProvider.overrideWith(_UnreachableProfilesNotifier.new),
    );

    // Not the default error card: the snapshot is rendered as a real tile, and
    // the failure names the server it could not reach.
    expect(find.text('Alex'), findsOneWidget);
    expect(
      find.text("Can't reach the server at nas.local — check your connection."),
      findsOneWidget,
    );
    // PrimaryPillButton uppercases its label.
    expect(find.text('RETRY'), findsOneWidget);

    await tester.tap(find.text('Alex'));
    await tester.pumpAndSettle();

    // Tapping it enters the session on that persona rather than dead-ending.
    expect(find.text('HOME'), findsOneWidget);
  });

  testWidgets('an unreachable server with no persisted profile still retries',
      (tester) async {
    await _pumpRoutedPicker(
      tester,
      const [],
      reduceMotion: true,
      profilesOverride:
          profilesProvider.overrideWith(_UnreachableProfilesNotifier.new),
    );

    expect(find.text('Profiles are unavailable'), findsOneWidget);
    expect(find.text('RETRY'), findsOneWidget);
  });

  testWidgets('the ceremony runs about five seconds end to end',
      (tester) async {
    await _pumpRoutedPicker(
      tester,
      [_profile(1, 'Alex', Mood.romantic)],
      reduceMotion: false,
    );

    await tester.tap(find.text('Alex'));
    await tester.pump();

    // Still mid-ceremony a moment before the configured full duration.
    await tester.pump(kProfileSelectionDuration - const Duration(milliseconds: 200));
    expect(find.text('HOME'), findsNothing);

    // And home has arrived shortly after it elapses.
    await tester.pumpAndSettle();
    expect(find.text('HOME'), findsOneWidget);
  });
}
