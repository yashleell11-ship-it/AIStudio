import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/content_mode/content_mode.dart';
import 'package:manhwamaniacs/features/content_mode/content_mode_controller.dart';
import 'package:manhwamaniacs/features/novels/providers/novels_gate_provider.dart';
import 'package:manhwamaniacs/features/profiles/models/mood.dart';
import 'package:manhwamaniacs/features/profiles/models/profile.dart';
import 'package:manhwamaniacs/features/profiles/providers/profiles_providers.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/test_overrides.dart';

class _SwitchableProfileNotifier extends ActiveProfileNotifier {
  static const profileOne =
      ActiveProfile(id: 1, name: 'One', avatarKey: null, mood: Mood.neutral);
  static const profileTwo =
      ActiveProfile(id: 2, name: 'Two', avatarKey: null, mood: Mood.neutral);

  @override
  ActiveProfile? build() => profileOne;

  void switchTo(ActiveProfile? profile) => state = profile;
}

class _NoProfileNotifier extends ActiveProfileNotifier {
  @override
  ActiveProfile? build() => null;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  Future<ProviderContainer> makeContainer({
    Map<String, Object> seeded = const {},
    bool novelsEnabled = true,
    bool withProfile = true,
  }) async {
    SharedPreferences.setMockInitialValues(seeded);
    final prefs = await SharedPreferences.getInstance();
    final container = ProviderContainer(
      overrides: [
        sharedPrefsProvider.overrideWithValue(prefs),
        authenticatedAuthOverride(), // user id 1
        novelsGateProvider.overrideWith((ref) async => novelsEnabled),
        novelsEnabledProvider.overrideWithValue(novelsEnabled),
        if (withProfile)
          activeProfileProvider.overrideWith(_SwitchableProfileNotifier.new)
        else
          activeProfileProvider.overrideWith(_NoProfileNotifier.new),
      ],
    );
    addTearDown(container.dispose);
    return container;
  }

  test('defaults to manga — what the owner reads daily', () async {
    final container = await makeContainer();
    expect(container.read(contentModeControllerProvider), ContentMode.manga);
  });

  test('setMode applies immediately and persists per (user, profile)', () async {
    final container = await makeContainer();
    await container
        .read(contentModeControllerProvider.notifier)
        .setMode(ContentMode.novel);

    expect(container.read(contentModeControllerProvider), ContentMode.novel);
    expect(
      container.read(sharedPrefsProvider).getString('mm.content-mode.u1p1'),
      'novel',
    );
  });

  test('a second persona does not inherit the first one\'s mode', () async {
    final container = await makeContainer(
      seeded: {'mm.content-mode.u1p1': 'novel'},
    );
    expect(container.read(contentModeControllerProvider), ContentMode.novel);

    final profiles = container.read(activeProfileProvider.notifier)
        as _SwitchableProfileNotifier;
    profiles.switchTo(_SwitchableProfileNotifier.profileTwo);
    // Profile two has never chosen a mode: it lands in manga, not in the
    // half-empty Novels app profile one left behind.
    expect(container.read(contentModeControllerProvider), ContentMode.manga);
  });

  test('the pre-profile states get a device slot, never a shared one', () async {
    final container = await makeContainer(withProfile: false);
    await container
        .read(contentModeControllerProvider.notifier)
        .setMode(ContentMode.novel);

    final prefs = container.read(sharedPrefsProvider);
    expect(prefs.getString('mm.content-mode.device'), 'novel');
    expect(prefs.getString('mm.content-mode.u1p1'), isNull);
  });

  group('with the novels flag off', () {
    test('a stored Novels mode does not come back as a half-empty app',
        () async {
      final container = await makeContainer(
        seeded: {'mm.content-mode.u1p1': 'novel'},
        novelsEnabled: false,
      );
      expect(container.read(contentModeControllerProvider), ContentMode.manga);
    });

    test('switching to Novels is refused rather than persisted', () async {
      final container = await makeContainer(novelsEnabled: false);
      await container
          .read(contentModeControllerProvider.notifier)
          .setMode(ContentMode.novel);

      expect(container.read(contentModeControllerProvider), ContentMode.manga);
      expect(
        container.read(sharedPrefsProvider).getString('mm.content-mode.u1p1'),
        isNull,
      );
    });

    test('the switch does not render and nothing is scoped', () async {
      final container = await makeContainer(novelsEnabled: false);
      final scope = container.read(contentModeScopeProvider);
      expect(scope.showSwitch, isFalse);
      expect(scope.mode, ContentMode.manga);
      // No /sources fetch is provoked just to build an index nobody needs.
      expect(scope.index, isEmpty);
    });
  });

  test('a corrupt stored value falls back rather than throwing', () async {
    final container = await makeContainer(
      seeded: {'mm.content-mode.u1p1': 'graphic-novel'},
    );
    expect(container.read(contentModeControllerProvider), ContentMode.manga);
  });
}
