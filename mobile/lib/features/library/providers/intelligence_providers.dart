import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/library/models/library_statistics.dart';
import 'package:manhwamaniacs/features/library/models/reading_history_item.dart';
import 'package:manhwamaniacs/features/library/models/followed_series.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

final statisticsProvider = FutureProvider.autoDispose<LibraryStatistics>((ref) async {
  final repo = ref.watch(libraryRepositoryProvider);
  final result = await repo.statistics();
  if (result.isErr) throw result.error;
  return result.value;
});

final recommendationsProvider =
    FutureProvider.autoDispose<List<FollowedSeries>>((ref) async {
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
  final sessionsResult = await repo.readingHistory();
  final calendarResult = await repo.readingCalendar();
  if (sessionsResult.isErr) throw sessionsResult.error;
  if (calendarResult.isErr) throw calendarResult.error;
  return ReadingHistoryData(
    sessions: sessionsResult.value,
    calendar: calendarResult.value,
  );
});
