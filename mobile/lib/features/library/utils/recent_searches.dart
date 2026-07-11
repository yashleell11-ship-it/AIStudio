import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

const recentSearchesKey = 'manhwamaniacs:recent-searches';
const maxRecentSearches = 4;

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

List<String> readRecentSearches(SharedPreferences prefs) {
  final raw = prefs.getString(recentSearchesKey);
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

Future<void> writeRecentSearch(SharedPreferences prefs, String term) async {
  final trimmed = term.trim();
  if (trimmed.length < 2) return;

  final existing = readRecentSearches(prefs)
      .where((item) => item.toLowerCase() != trimmed.toLowerCase())
      .toList();
  final next = [trimmed, ...existing].take(maxRecentSearches).toList();
  await prefs.setString(recentSearchesKey, jsonEncode(next));
}
