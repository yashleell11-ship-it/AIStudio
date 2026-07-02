import 'dart:convert';

import 'package:aistudio_mobile/features/library/models/library_query.dart';
import 'package:shared_preferences/shared_preferences.dart';

const libraryQueryPrefsKey = 'aistudio:library-query';

LibraryQuery readLibraryQuery(SharedPreferences prefs) {
  final raw = prefs.getString(libraryQueryPrefsKey);
  if (raw == null || raw.isEmpty) return const LibraryQuery();

  try {
    final parsed = jsonDecode(raw);
    if (parsed is! Map) return const LibraryQuery();

    final sortName = parsed['sort'] as String?;
    final filterName = parsed['filter'] as String?;
    final viewModeName = parsed['viewMode'] as String?;
    final favoritesOnly = parsed['favoritesOnly'] as bool? ?? false;

    return LibraryQuery(
      sort: _parseEnum(LibrarySort.values, sortName, LibrarySort.recent),
      filter: _parseFilter(filterName),
      favoritesOnly: favoritesOnly,
      viewMode: _parseEnum(
        LibraryViewMode.values,
        viewModeName,
        LibraryViewMode.grid,
      ),
    );
  } catch (_) {
    return const LibraryQuery();
  }
}

Future<void> writeLibraryQuery(
  SharedPreferences prefs,
  LibraryQuery query,
) async {
  await prefs.setString(
    libraryQueryPrefsKey,
    jsonEncode({
      'sort': query.sort.name,
      'filter': query.filter.name,
      'favoritesOnly': query.favoritesOnly,
      'viewMode': query.viewMode.name,
    }),
  );
}

LibraryFilter _parseFilter(String? value) {
  if (value == null) return LibraryFilter.all;
  if (value == 'unread') return LibraryFilter.all;
  return _parseEnum(LibraryFilter.values, value, LibraryFilter.all);
}

T _parseEnum<T>(List<T> values, String? name, T fallback) {
  if (name == null) return fallback;
  for (final value in values) {
    if (value is Enum && value.name == name) return value;
  }
  return fallback;
}

bool libraryQueryPersistedFieldsChanged(LibraryQuery before, LibraryQuery after) =>
    before.sort != after.sort ||
    before.filter != after.filter ||
    before.favoritesOnly != after.favoritesOnly ||
    before.viewMode != after.viewMode;
