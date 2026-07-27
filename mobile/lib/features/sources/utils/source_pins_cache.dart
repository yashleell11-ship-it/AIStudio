import 'dart:convert';

import 'package:manhwamaniacs/features/sources/models/source_pin.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Local persistence for source pins.
///
/// The server owns the pins; everything here is either a write-through cache of
/// the last server answer (so an offline launch doesn't reorder the Sources
/// screen) or the one-shot migration off the old device-global preference.
///
/// Keys are written from a sources-owned file rather than added to
/// `PreferencesService` because that file belongs to another workstream; the
/// naming follows the same `manhwamaniacs:` scheme as `recent_searches.dart`.
const sourcePinsCacheKey = 'manhwamaniacs:source-pins';

/// Device-global one-shot flag for the SharedPreferences → server migration.
const sourcePinsMigratedKey = 'pinned_sources_migrated';

/// The pre-server key. Device-global and un-scoped, which is exactly why it is
/// being retired: account B on the same phone inherited account A's pins.
const legacyPinnedSourcesKey = 'pinned_sources';

/// Cache key for one `(account, profile)` scope.
///
/// Both ids are in the key because a library belongs to both axes. Profile ids
/// alone would not do: `reading_profiles.id` is a global autoincrement, so
/// profile 3 of account A and profile 3 of account B would collide on one key.
String sourcePinsCacheKeyFor({required int? userId, required int? profileId}) =>
    '$sourcePinsCacheKey:${userId ?? 'anon'}:${profileId ?? 'default'}';

List<SourcePin> readCachedSourcePins(SharedPreferences prefs, String key) {
  final raw = prefs.getString(key);
  if (raw == null || raw.isEmpty) return const [];
  try {
    final parsed = jsonDecode(raw);
    if (parsed is! List) return const [];
    return parsed
        .whereType<Map<String, dynamic>>()
        .map(SourcePin.fromJson)
        .toList();
  } catch (_) {
    return const [];
  }
}

Future<void> writeCachedSourcePins(
  SharedPreferences prefs,
  String key,
  List<SourcePin> pins,
) =>
    prefs.setString(key, jsonEncode([for (final pin in pins) pin.toJson()]));

bool sourcePinsMigrated(SharedPreferences prefs) =>
    prefs.getBool(sourcePinsMigratedKey) ?? false;

List<String> readLegacyPinnedSources(SharedPreferences prefs) =>
    prefs.getStringList(legacyPinnedSourcesKey) ?? const [];

/// Close the migration for good.
///
/// The legacy list is dropped along with the flag being set: leaving it behind
/// would let a cleared flag re-seed a *different* account's pins from whatever
/// the first account happened to pin on this device.
Future<void> completeSourcePinsMigration(SharedPreferences prefs) async {
  await prefs.setBool(sourcePinsMigratedKey, true);
  await prefs.remove(legacyPinnedSourcesKey);
}
