import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/settings/models/app_changelog.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';

/// Fetches the backend `/app/changelog` release notes (newest first).
///
/// Returns an empty list if the backend is unreachable or the payload is
/// malformed, so the "What's new" surface degrades gracefully offline.
final appChangelogProvider =
    FutureProvider.autoDispose<List<ChangelogRelease>>((ref) async {
  final dio = ref.watch(dioProvider);

  try {
    final response = await dio.get<Map<String, dynamic>>('/app/changelog');
    final entries = response.data?['entries'];
    if (entries is! List) return const [];
    return entries
        .whereType<Map<String, dynamic>>()
        .map(ChangelogRelease.fromJson)
        .toList(growable: false);
  } on DioException {
    return const [];
  } catch (_) {
    return const [];
  }
});
