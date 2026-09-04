import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/auth/models/auth_state.dart';
import 'package:manhwamaniacs/features/auth/providers/auth_controller.dart';
import 'package:manhwamaniacs/features/novels/models/novel_palette.dart';
import 'package:manhwamaniacs/features/novels/models/novel_typography.dart';
import 'package:manhwamaniacs/features/profiles/providers/profiles_providers.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';

/// Type settings for one book.
class NovelPreferences {
  const NovelPreferences({
    this.fontSize = kDefaultNovelFontSize,
    this.lineHeight = kDefaultNovelLineHeight,
    this.measure = kDefaultNovelMeasure,
    this.fontFamily = NovelFontFamily.serif,
  });

  final double fontSize;
  final double lineHeight;

  /// Column width in characters — see `models/novel_typography.dart`.
  final double measure;
  final NovelFontFamily fontFamily;

  NovelPreferences copyWith({
    double? fontSize,
    double? lineHeight,
    double? measure,
    NovelFontFamily? fontFamily,
  }) =>
      NovelPreferences(
        fontSize: clampNovelFontSize(fontSize ?? this.fontSize),
        lineHeight: clampNovelLineHeight(lineHeight ?? this.lineHeight),
        measure: clampNovelMeasure(measure ?? this.measure),
        fontFamily: fontFamily ?? this.fontFamily,
      );

  Map<String, dynamic> toJson() => {
        'fontSize': fontSize,
        'lineHeight': lineHeight,
        'measure': measure,
        'fontFamily': fontFamily.wire,
      };

  /// Clamped on the way IN, not only on the way out: these are persisted, and
  /// a value that drifted out of range (a bad write, a hand-edited store, a
  /// range that narrowed in a later release) would otherwise follow the reader
  /// around forever.
  factory NovelPreferences.fromJson(Map<String, dynamic> json) =>
      NovelPreferences(
        fontSize: clampNovelFontSize(
          (json['fontSize'] as num?)?.toDouble() ?? kDefaultNovelFontSize,
        ),
        lineHeight: clampNovelLineHeight(
          (json['lineHeight'] as num?)?.toDouble() ?? kDefaultNovelLineHeight,
        ),
        measure: clampNovelMeasure(
          (json['measure'] as num?)?.toDouble() ?? kDefaultNovelMeasure,
        ),
        fontFamily: NovelFontFamily.fromWire(json['fontFamily'] as String?),
      );
}

/// Typography, per SERIES — the same split the manga reader draws between its
/// per-series mode/fit/zoom and its app-wide defaults.
///
/// A dense translated web novel wants a bigger face and looser leading than a
/// crisply edited original; a reader who tuned one should not have to re-tune
/// it every time they move between the two. So size / leading / measure / face
/// are keyed by series.
///
/// The reading PALETTE deliberately does not live here — it is a property of
/// the room and the hour, not of the book, so it is per-profile
/// ([novelPaletteControllerProvider]).
///
/// Scoped per `(user, profile)` like every other on-device preference: two
/// personas on one phone read different things, and inheriting a sibling's
/// setup is both wrong and a small disclosure that the sibling reads that
/// series at all.
final novelPreferencesControllerProvider = NotifierProvider.family<
    NovelPreferencesController, NovelPreferences, String>(
  NovelPreferencesController.new,
  name: 'novelPreferences',
);

/// Stable per-series key: the opaque `(sourceId, seriesKey)` pair, joined the
/// same way the manga reader's scroll-storage key is.
String novelSeriesPrefsKey(String sourceId, String seriesKey) =>
    '$sourceId:$seriesKey';

class NovelPreferencesController
    extends FamilyNotifier<NovelPreferences, String> {
  static const String _keyPrefix = 'mm.novel-prefs.';
  static const String _deviceKey = 'mm.novel-prefs.device';

  @override
  NovelPreferences build(String seriesKey) {
    final prefs = ref.watch(sharedPrefsProvider);
    final raw = prefs.getString(_storageKey(watch: true));
    return _readStore(raw)[seriesKey] ?? const NovelPreferences();
  }

  Future<void> update(NovelPreferences next) async {
    state = next;
    final prefs = ref.read(sharedPrefsProvider);
    final key = _storageKey(watch: false);
    final store = _readStore(prefs.getString(key));
    store[arg] = next;
    await prefs.setString(
      key,
      jsonEncode({for (final e in store.entries) e.key: e.value.toJson()}),
    );
  }

  Future<void> setFontSize(double value) =>
      update(state.copyWith(fontSize: value));

  Future<void> setLineHeight(double value) =>
      update(state.copyWith(lineHeight: value));

  Future<void> setMeasure(double value) =>
      update(state.copyWith(measure: value));

  Future<void> setFontFamily(NovelFontFamily value) =>
      update(state.copyWith(fontFamily: value));

  /// One map for every series this persona has tuned. A corrupt blob resolves
  /// to an empty store rather than throwing: type settings are a convenience,
  /// and losing them must never be the reason a chapter refuses to open.
  Map<String, NovelPreferences> _readStore(String? raw) {
    if (raw == null || raw.isEmpty) return {};
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map) return {};
      return {
        for (final entry in decoded.entries)
          if (entry.value is Map)
            entry.key as String: NovelPreferences.fromJson(
              Map<String, dynamic>.from(entry.value as Map),
            ),
      };
    } catch (_) {
      return {};
    }
  }

  String _storageKey({required bool watch}) =>
      _scopedKey(ref, prefix: _keyPrefix, deviceKey: _deviceKey, watch: watch);
}

/// The reading palette, per PROFILE.
///
/// Unlike typography (which is about the book), the surface a page is painted
/// on is about the room, the hour and the reader's eyes. It should follow
/// someone from novel to novel, exactly as the manga reader's dimmer and
/// warmth do.
///
/// The stored value is a palette id, [NovelPalettes.followAppId], or nothing
/// at all — and "nothing at all" is a real state, not a missing value: it
/// means "never chose one", and only then does the app's own light/dark seed
/// Paper or Dusk. An explicit choice is never overridden by a theme change,
/// because a palette that flips when the app's theme flips is not an
/// independent palette.
final novelPaletteControllerProvider =
    NotifierProvider<NovelPaletteController, String?>(
  NovelPaletteController.new,
  name: 'novelPalette',
);

class NovelPaletteController extends Notifier<String?> {
  static const String _keyPrefix = 'mm.novel-palette.';
  static const String _deviceKey = 'mm.novel-palette.device';

  @override
  String? build() {
    final prefs = ref.watch(sharedPrefsProvider);
    final stored = prefs.getString(_storageKey(watch: true));
    return NovelPalettes.isChoice(stored) ? stored : null;
  }

  Future<void> setChoice(String choice) async {
    if (!NovelPalettes.isChoice(choice)) return;
    state = choice;
    await ref
        .read(sharedPrefsProvider)
        .setString(_storageKey(watch: false), choice);
  }

  String _storageKey({required bool watch}) =>
      _scopedKey(ref, prefix: _keyPrefix, deviceKey: _deviceKey, watch: watch);
}

/// `"{prefix}u{userId}p{profileId}"`, or [deviceKey] outside a session.
///
/// The same scope-id convention as the on-device chapter store and the theme
/// controller — one format for all per-persona device state, so there is one
/// shape to get wrong rather than three. `watch` is true from a `build` (so
/// profile and account switches recompute) and false from a write (which must
/// not add dependencies).
String _scopedKey(
  Ref ref, {
  required String prefix,
  required String deviceKey,
  required bool watch,
}) {
  int? selectUserId(AuthState auth) =>
      auth is AuthAuthenticated ? auth.user.id : null;
  final userId = watch
      ? ref.watch(authControllerProvider.select(selectUserId))
      : selectUserId(ref.read(authControllerProvider));
  final profileId = watch
      ? ref.watch(activeProfileProvider.select((p) => p?.id))
      : ref.read(activeProfileProvider)?.id;
  if (userId == null || profileId == null) return deviceKey;
  return '${prefix}u${userId}p$profileId';
}
