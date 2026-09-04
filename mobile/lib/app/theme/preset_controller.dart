import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_metrics.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/features/auth/models/auth_state.dart';
import 'package:manhwamaniacs/features/auth/providers/auth_controller.dart';
import 'package:manhwamaniacs/features/profiles/providers/profiles_providers.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';

/// The design preset the app is currently shaped by.
///
/// Deliberately a mirror of `ThemeController`, because the two settings are
/// the same kind of thing: personal to a reading persona, so the selection
/// persists under a per-`(user, profile)` key using the `u{userId}p{profileId}`
/// scope-id convention shared with the on-device chapter store. Watching auth
/// and the active profile means switching personas re-reads the incoming one's
/// preset automatically; the pre-profile states (login, setup, picker) fall
/// back to a device-level slot, empty on a fresh install and therefore
/// resolving to Signature.
///
/// Kept as a separate provider from the theme rather than folded into one
/// "appearance" object: colour and shape are orthogonal axes, and a persona
/// that has chosen Nord must keep it when it changes preset.
final presetControllerProvider = NotifierProvider<PresetController, AppMetrics>(
  PresetController.new,
  name: 'presetController',
);

class PresetController extends Notifier<AppMetrics> {
  static const String _keyPrefix = 'mm.preset.';

  /// Fallback slot for the pre-profile states so a choice made there isn't
  /// lost, without ever leaking one persona's preset to another.
  static const String _deviceKey = 'mm.preset.device';

  @override
  AppMetrics build() {
    final prefs = ref.watch(sharedPrefsProvider);
    return AppPresets.byId(prefs.getString(_storageKey(watch: true)));
  }

  /// Apply and persist [id] for the active persona. Unknown ids are ignored:
  /// byId falls back to Signature for *reads*, where a stale persisted id must
  /// not brick startup, but a live tap on a bad id should be a no-op rather
  /// than a silent reset of the owner's chosen design.
  Future<void> setPreset(String id) async {
    if (!AppPresets.all.any((p) => p.id == id)) return;
    state = AppPresets.byId(id);
    await ref.read(sharedPrefsProvider).setString(_storageKey(watch: false), id);
  }

  /// The preference key for the current session scope. `watch` is true from
  /// [build] (so profile/account switches recompute the preset) and false from
  /// [setPreset] (a write must not add dependencies).
  String _storageKey({required bool watch}) {
    int? selectUserId(AuthState auth) =>
        auth is AuthAuthenticated ? auth.user.id : null;
    final userId = watch
        ? ref.watch(authControllerProvider.select(selectUserId))
        : selectUserId(ref.read(authControllerProvider));
    final profileId = watch
        ? ref.watch(activeProfileProvider.select((p) => p?.id))
        : ref.read(activeProfileProvider)?.id;
    if (userId == null || profileId == null) return _deviceKey;
    return '${_keyPrefix}u${userId}p$profileId';
  }
}
