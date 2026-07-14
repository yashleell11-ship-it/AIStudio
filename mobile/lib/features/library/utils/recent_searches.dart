import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

const recentSearchesKey = 'manhwamaniacs:recent-searches';
const maxRecentSearches = 4;

/// Builds the SharedPreferences key for a profile's recent-search history.
///
/// Passing a null [profileId] returns the legacy global key so callers (and
/// tests) that predate profile scoping keep working; a non-null id namespaces
/// the history per profile so switching the active reading profile no longer
/// leaks profile A's terms onto profile B's Search screen.
String recentSearchesKeyFor(int? profileId) =>
    profileId == null ? recentSearchesKey : '$recentSearchesKey:$profileId';

const trendingSearchSuggestions = [
  'fantasy',
  'romance',
  'action',
  'manhwa',
  'manga',
  'webtoon',
  'horror',
  'sci-fi',
];

List<String> readRecentSearches(SharedPreferences prefs, {int? profileId}) {
  final raw = prefs.getString(recentSearchesKeyFor(profileId));
  if (raw == null || raw.isEmpty) return [];

  try {
    final parsed = jsonDecode(raw);
    if (parsed is! List) return [];
    return parsed
        .whereType<String>()
        .map((item) => item.trim())
        .where((item) => item.isNotEmpty)
        .take(maxRecentSearches)
        .toList();
  } catch (_) {
    return [];
  }
}

Future<void> writeRecentSearch(
  SharedPreferences prefs,
  String term, {
  int? profileId,
}) async {
  final trimmed = term.trim();
  if (trimmed.length < 2) return;

  final existing = readRecentSearches(prefs, profileId: profileId)
      .where((item) => item.toLowerCase() != trimmed.toLowerCase())
      .toList();
  final next = [trimmed, ...existing].take(maxRecentSearches).toList();
  await prefs.setString(recentSearchesKeyFor(profileId), jsonEncode(next));
}
