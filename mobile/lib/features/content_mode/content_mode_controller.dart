import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/auth/models/auth_state.dart';
import 'package:manhwamaniacs/features/auth/providers/auth_controller.dart';
import 'package:manhwamaniacs/features/content_mode/content_mode.dart';
import 'package:manhwamaniacs/features/novels/providers/novels_gate_provider.dart';
import 'package:manhwamaniacs/features/profiles/providers/profiles_providers.dart';
import 'package:manhwamaniacs/features/sources/providers/sources_provider.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';

/// The active profile's content mode.
///
/// Persisted per `(user, profile)` under the same `u{userId}p{profileId}`
/// scope-id convention the on-device chapter store and the theme controller
/// use — one format for all per-persona device state. Because [build] *watches*
/// the auth user and the active profile, switching profiles re-reads the
/// incoming persona's mode automatically: two personas on one phone have
/// different libraries, and one of them living in Novels mode must not decide
/// what the other sees when they pick the phone up.
///
/// Signing out (or having no profile picked yet) falls back to a device-level
/// key, which is empty on a fresh install and therefore resolves to manga.
final contentModeControllerProvider =
    NotifierProvider<ContentModeController, ContentMode>(
  ContentModeController.new,
  name: 'contentMode',
);

class ContentModeController extends Notifier<ContentMode> {
  static const String _keyPrefix = 'mm.content-mode.';

  /// Fallback slot for the pre-profile states, so a choice made there is not
  /// lost without ever leaking one persona's mode to another.
  static const String _deviceKey = 'mm.content-mode.device';

  @override
  ContentMode build() {
    final prefs = ref.watch(sharedPrefsProvider);
    final novelsEnabled = ref.watch(novelsEnabledProvider);
    final stored = ContentMode.parse(prefs.getString(_storageKey(watch: true)));
    return resolveContentMode(stored, novelsEnabled: novelsEnabled);
  }

  /// Switch the whole app to [mode] and remember it for this persona.
  ///
  /// A no-op when the mode has not changed, and a no-op for
  /// [ContentMode.novel] while the gate is shut — the switch does not render
  /// in that case, so reaching here would mean something else went wrong and
  /// silently forcing manga is the safe answer.
  Future<void> setMode(ContentMode mode) async {
    if (mode == ContentMode.novel && !ref.read(novelsEnabledProvider)) return;
    if (state == mode) return;
    state = mode;
    await ref
        .read(sharedPrefsProvider)
        .setString(_storageKey(watch: false), mode.wire);
  }

  /// The preference key for the current session scope. `watch` is true from
  /// [build] (so profile/account switches recompute the mode) and false from
  /// [setMode] (a write must not add dependencies).
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
    return '$_keyPrefix' 'u${userId}p$profileId';
  }
}

/// `source_id -> ContentMode` for every installed source.
///
/// Built from the sources listing the app already fetches, so scoping a
/// library row — which carries a source id and no kind — costs no extra
/// request. An empty index (list not loaded, or offline) resolves every row to
/// manga, which is the deliberate fail-open in [matchesContentMode].
///
/// `autoDispose`, and short-circuited to an empty index when the gate is shut,
/// for one reason each. Auto-disposing because [sourcesListProvider] is itself
/// `autoDispose` and a keep-alive watcher would pin it for the life of the app,
/// quietly turning "the Sources tab refetches when you come back to it" into
/// "it never does". Short-circuiting because with novels off there is nothing
/// to scope, and a screen that reads this must not become the reason
/// `/sources` is fetched at all.
final sourceModeIndexProvider = Provider.autoDispose<Map<String, ContentMode>>(
  (ref) {
    if (!ref.watch(novelsEnabledProvider)) return const {};
    return buildSourceModeIndex(ref.watch(sourcesListProvider).valueOrNull);
  },
  name: 'sourceModeIndex',
);

/// Everything a list needs to scope itself, resolved once.
///
/// Screens watch this rather than the three providers separately, so the mode,
/// the index and the gate can never be read at different moments and disagree
/// mid-build.
class ContentModeScope {
  const ContentModeScope({
    required this.mode,
    required this.index,
    required this.novelsEnabled,
  });

  final ContentMode mode;
  final Map<String, ContentMode> index;
  final bool novelsEnabled;

  bool get isNovel => mode == ContentMode.novel;

  /// Whether the Manga/Novels switch should render at all.
  bool get showSwitch => novelsEnabled;

  List<T> filter<T>(List<T> rows, String? Function(T row) sourceIdOf) =>
      filterByContentMode(
        rows,
        index,
        mode,
        sourceIdOf: sourceIdOf,
        novelsEnabled: novelsEnabled,
      );

  /// The mode a row from [sourceId] belongs to — for a row list that groups
  /// rather than filters (the Downloads screen).
  ContentMode modeOf(String? sourceId) =>
      sourceId == null ? ContentMode.manga : (index[sourceId] ?? ContentMode.manga);
}

final contentModeScopeProvider = Provider.autoDispose<ContentModeScope>(
  (ref) => ContentModeScope(
    mode: ref.watch(contentModeControllerProvider),
    index: ref.watch(sourceModeIndexProvider),
    novelsEnabled: ref.watch(novelsEnabledProvider),
  ),
  name: 'contentModeScope',
);
