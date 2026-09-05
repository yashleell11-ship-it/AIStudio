import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_palette.dart';
import 'package:manhwamaniacs/app/theme/app_palettes.dart';
import 'package:manhwamaniacs/features/auth/models/auth_state.dart';
import 'package:manhwamaniacs/features/auth/providers/auth_controller.dart';
import 'package:manhwamaniacs/features/profiles/providers/profiles_providers.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';

/// The palette the app is currently wearing.
///
/// The selection is personal to a reading persona, so it persists under a
/// per-`(user, profile)` key using the same `u{userId}p{profileId}` scope-id
/// convention as the on-device chapter store (`downloads_scope.dart`) — one
/// format for all per-persona device state. Because [ThemeController.build]
/// *watches* the auth user and active profile, switching profiles re-reads
/// the incoming persona's saved theme automatically; signing out (or having
/// no profile picked yet) falls back to a device-level key, which is empty on
/// a fresh install and therefore resolves to [AppPalettes.defaultPalette].
///
/// Themes stay per-persona: moving the default moves only the unset case. A
/// profile with a stored id keeps reading that id from its own key, and the
/// key is derived from the watched `(user, profile)` pair, so the switch
/// between two personas swaps palettes rather than sharing one.
final themeControllerProvider = NotifierProvider<ThemeController, AppPalette>(
  ThemeController.new,
  name: 'themeController',
);

class ThemeController extends Notifier<AppPalette> {
  static const String _keyPrefix = 'mm.theme.';

  /// Fallback slot for the pre-profile states (login, setup, picker) so a
  /// choice made there isn't lost, without ever leaking one persona's theme
  /// to another.
  static const String _deviceKey = 'mm.theme.device';

  @override
  AppPalette build() {
    final prefs = ref.watch(sharedPrefsProvider);
    return AppPalettes.byId(prefs.getString(_storageKey(watch: true)));
  }

  /// Apply and persist [id] for the active persona. Unknown ids are ignored
  /// (byId falls back to the default only for *reads*, where a stale persisted
  /// id must not brick startup — a live tap on a bad id should be a no-op).
  Future<void> setTheme(String id) async {
    if (!AppPalettes.all.any((p) => p.id == id)) return;
    state = AppPalettes.byId(id);
    await ref.read(sharedPrefsProvider).setString(_storageKey(watch: false), id);
  }

  /// The preference key for the current session scope. `watch` is true from
  /// [build] (so profile/account switches recompute the theme) and false from
  /// [setTheme] (a write must not add dependencies).
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
