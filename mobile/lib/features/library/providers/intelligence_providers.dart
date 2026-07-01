import 'package:aistudio_mobile/features/library/models/library_statistics.dart';
import 'package:aistudio_mobile/features/library/models/reading_history_item.dart';
import 'package:aistudio_mobile/features/library/models/series_summary.dart';
import 'package:aistudio_mobile/shared/providers/repository_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

final statisticsProvider = FutureProvider.autoDispose<LibraryStatistics>((ref) async {
  final repo = ref.watch(libraryRepositoryProvider);
  final result = await repo.statistics();
  if (result.isErr) throw result.error;
  return result.value;
});

final recommendationsProvider =
    FutureProvider.autoDispose<List<SeriesSummary>>((ref) async {
  final repo = ref.watch(libraryRepositoryProvider);
  final result = await repo.recommendations(limit: 12);
  if (result.isErr) throw result.error;
  return result.value;
});

class ReadingHistoryData {
  const ReadingHistoryData({
    required this.sessions,
    required this.calendar,
  });

  final List<ReadingHistoryItem> sessions;
  final List<ReadingCalendarDay> calendar;
}

final readingHistoryProvider =
    FutureProvider.autoDispose<ReadingHistoryData>((ref) async {
  final repo = ref.watch(libraryRepositoryProvider);
  final sessionsResult = await repo.readingHistory(limit: 50);
  final calendarResult = await repo.readingCalendar(days: 30);
  if (sessionsResult.isErr) throw sessionsResult.error;
  if (calendarResult.isErr) throw calendarResult.error;
  return ReadingHistoryData(
    sessions: sessionsResult.value,
    calendar: calendarResult.value,
  );
});
