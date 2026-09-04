import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/app/theme/preset_controller.dart';
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

  test('defaults to Signature when nothing is persisted', () async {
    final container = await makeContainer();
    expect(container.read(presetControllerProvider), AppPresets.signature);
  });

  test('setPreset applies immediately and persists per (user, profile)',
      () async {
    final container = await makeContainer();
    await container.read(presetControllerProvider.notifier).setPreset('compact');

    expect(container.read(presetControllerProvider), AppPresets.compact);
    expect(
      container.read(sharedPrefsProvider).getString('mm.preset.u1p1'),
      'compact',
    );
  });

  test('an unknown id is a no-op, not a reset', () async {
    final container = await makeContainer();
    final controller = container.read(presetControllerProvider.notifier);
    await controller.setPreset('editorial');
    await controller.setPreset('definitely_not_a_preset');

    expect(container.read(presetControllerProvider), AppPresets.editorial);
    expect(
      container.read(sharedPrefsProvider).getString('mm.preset.u1p1'),
      'editorial',
    );
  });

  test('a corrupt persisted id falls back to Signature', () async {
    final container =
        await makeContainer(seeded: {'mm.preset.u1p1': 'deleted_preset'});
    expect(container.read(presetControllerProvider), AppPresets.signature);
  });

  test('switching profiles switches to that persona\'s saved design', () async {
    final container = await makeContainer(
      seeded: {
        'mm.preset.u1p1': 'cinema',
        'mm.preset.u1p2': 'matte',
      },
    );
    expect(container.read(presetControllerProvider), AppPresets.cinema);

    final profiles = container.read(activeProfileProvider.notifier)
        as _SwitchableProfileNotifier;
    profiles.switchTo(_SwitchableProfileNotifier.profileTwo);

    expect(container.read(presetControllerProvider), AppPresets.matte);
  });

  test('a persona with no saved design gets the default, not a neighbour\'s',
      () async {
    final container = await makeContainer(seeded: {'mm.preset.u1p1': 'cinema'});
    final profiles = container.read(activeProfileProvider.notifier)
        as _SwitchableProfileNotifier;
    profiles.switchTo(_SwitchableProfileNotifier.profileTwo);

    expect(container.read(presetControllerProvider), AppPresets.signature);
  });

  test('no active profile: reads and writes the device slot', () async {
    final container = await makeContainer(
      withProfile: false,
      seeded: {'mm.preset.device': 'editorial'},
    );
    expect(container.read(presetControllerProvider), AppPresets.editorial);

    await container.read(presetControllerProvider.notifier).setPreset('matte');
    expect(
      container.read(sharedPrefsProvider).getString('mm.preset.device'),
      'matte',
    );
    // The per-profile slots are untouched.
    expect(
      container.read(sharedPrefsProvider).getString('mm.preset.u1p1'),
      isNull,
    );
  });

  test('theme and design are independent settings on independent keys',
      () async {
    // The orthogonality promise, at the persistence layer: choosing a design
    // must not disturb the palette, and the two live in separate slots so one
    // can never overwrite the other.
    final container = await makeContainer(seeded: {'mm.theme.u1p1': 'nord'});
    await container.read(presetControllerProvider.notifier).setPreset('compact');

    final prefs = container.read(sharedPrefsProvider);
    expect(prefs.getString('mm.theme.u1p1'), 'nord');
    expect(prefs.getString('mm.preset.u1p1'), 'compact');
  });
}
