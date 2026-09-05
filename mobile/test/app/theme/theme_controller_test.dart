import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/app/theme/app_palettes.dart';
import 'package:manhwamaniacs/app/theme/app_palettes.generated.dart';
import 'package:manhwamaniacs/app/theme/theme_controller.dart';
import 'package:manhwamaniacs/features/profiles/models/mood.dart';
import 'package:manhwamaniacs/features/profiles/models/profile.dart';
import 'package:manhwamaniacs/features/profiles/providers/profiles_providers.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/test_overrides.dart';

/// The active-profile notifier, but steerable from a test so a persona switch
/// can be simulated without the picker ceremony (which needs the network).
class _SwitchableProfileNotifier extends ActiveProfileNotifier {
  static const profileOne =
      ActiveProfile(id: 1, name: 'One', avatarKey: null, mood: Mood.neutral);
  static const profileTwo =
      ActiveProfile(id: 2, name: 'Two', avatarKey: null, mood: Mood.neutral);

  @override
  ActiveProfile? build() => profileOne;

  void switchTo(ActiveProfile? profile) => state = profile;
}

/// No profile selected — the signed-out / pre-picker shape.
class _NoProfileNotifier extends ActiveProfileNotifier {
  @override
  ActiveProfile? build() => null;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  Future<ProviderContainer> makeContainer({
    Map<String, Object> seeded = const {},
    bool withProfile = true,
  }) async {
    SharedPreferences.setMockInitialValues(seeded);
    final prefs = await SharedPreferences.getInstance();
    final container = ProviderContainer(
      overrides: [
        sharedPrefsProvider.overrideWithValue(prefs),
        authenticatedAuthOverride(), // user id 1
        if (withProfile)
          activeProfileProvider.overrideWith(_SwitchableProfileNotifier.new)
        else
          activeProfileProvider.overrideWith(_NoProfileNotifier.new),
      ],
    );
    addTearDown(container.dispose);
    return container;
  }

  test('defaults to the app default when nothing is persisted', () async {
    final container = await makeContainer();
    expect(container.read(themeControllerProvider), AppPalettes.defaultPalette);
  });

  test('setTheme applies immediately and persists per (user, profile)', () async {
    final container = await makeContainer();
    await container.read(themeControllerProvider.notifier).setTheme('nord');

    expect(container.read(themeControllerProvider), Base16Palettes.nord);
    final prefs = container.read(sharedPrefsProvider);
    expect(prefs.getString('mm.theme.u1p1'), 'nord');
  });

  test('an unknown id is a no-op, not a reset', () async {
    final container = await makeContainer();
    final controller = container.read(themeControllerProvider.notifier);
    await controller.setTheme('mocha');
    await controller.setTheme('definitely_not_a_theme');

    expect(container.read(themeControllerProvider), Base16Palettes.mocha);
    expect(
      container.read(sharedPrefsProvider).getString('mm.theme.u1p1'),
      'mocha',
    );
  });

  test('a corrupt persisted id falls back to the default', () async {
    final container =
        await makeContainer(seeded: {'mm.theme.u1p1': 'deleted_theme'});
    expect(container.read(themeControllerProvider), AppPalettes.defaultPalette);
  });

  test('switching profiles switches to that persona\'s saved theme', () async {
    final container = await makeContainer(
      seeded: {
        'mm.theme.u1p1': 'gruvbox',
        'mm.theme.u1p2': 'latte',
      },
    );
    expect(container.read(themeControllerProvider), Base16Palettes.gruvbox);

    final profiles = container.read(activeProfileProvider.notifier)
        as _SwitchableProfileNotifier;
    profiles.switchTo(_SwitchableProfileNotifier.profileTwo);

    expect(container.read(themeControllerProvider), Base16Palettes.latte);
  });

  test('a persona with no saved theme gets the default, not a neighbour\'s',
      () async {
    final container = await makeContainer(seeded: {'mm.theme.u1p1': 'dracula'});
    final profiles = container.read(activeProfileProvider.notifier)
        as _SwitchableProfileNotifier;
    profiles.switchTo(_SwitchableProfileNotifier.profileTwo);

    expect(container.read(themeControllerProvider), AppPalettes.defaultPalette);
  });

  test('no active profile: reads and writes the device slot', () async {
    final container = await makeContainer(
      withProfile: false,
      seeded: {'mm.theme.device': 'rose_pine'},
    );
    expect(container.read(themeControllerProvider), Base16Palettes.rosePine);

    await container.read(themeControllerProvider.notifier).setTheme('paper');
    expect(
      container.read(sharedPrefsProvider).getString('mm.theme.device'),
      'paper',
    );
    // The per-profile slots are untouched.
    expect(
      container.read(sharedPrefsProvider).getString('mm.theme.u1p1'),
      isNull,
    );
  });
}
