/// `GET /library/statistics` — library shape plus everything
/// `reading_sessions` recorded (`FollowedSeriesService.statistics`, which
/// delegates the session aggregation to `ReadingStatsService.build`).
///
/// The first four fields are the original payload and keep their meaning. The
/// session-derived fields all carry empty defaults so a fixture that sets only
/// the counters — or a response from a backend that predates the aggregation —
/// parses into an honest "nothing recorded" rather than throwing.
class LibraryStatistics {
  const LibraryStatistics({
    required this.followedTotal,
    required this.favorites,
    required this.byReadingStatus,
    required this.chaptersCompleted,
    this.rangeDays = 30,
    this.totals = const ReadingTotals(),
    this.window = const ReadingTotals(),
    this.streak = const ReadingStreak(),
    this.daily = const [],
    this.byHour = const [],
    this.bySource = const [],
    this.bySeries = const [],
    this.recentSessions = const [],
  });

  /// Series this profile follows.
  final int followedTotal;
  final int favorites;
  final Map<String, int> byReadingStatus;

  /// Chapters *finished* (`chapter_progress.is_completed`) — a different
  /// number from [ReadingTotals.chaptersRead], and both are honest: this one
  /// includes chapters finished before session recording existed, that one
  /// counts only chapters a recorded session touched.
  final int chaptersCompleted;

  /// Length of the window [window], [daily], [byHour], [bySource] and
  /// [bySeries] cover. [totals], [streak] and [recentSessions] are all-time.
  final int rangeDays;

  final ReadingTotals totals;
  final ReadingTotals window;
  final ReadingStreak streak;

  /// One entry per day of the window, oldest first — dense, so a day off is a
  /// zero rather than a missing point a chart would draw straight through.
  final List<DailyActivity> daily;

  /// Always 24 entries (hour 0..23) when the backend answered.
  final List<HourActivity> byHour;

  final List<SourceActivity> bySource;
  final List<SeriesActivity> bySeries;
  final List<RecentSession> recentSessions;

  /// Whether any reading session has *ever* been recorded for this profile.
  ///
  /// The screen's fork: a profile with no sessions is told how statistics get
  /// filled in, instead of being shown a wall of honest-but-useless zeroes.
  bool get hasReadingHistory => totals.sessions > 0;

  /// Whether the window itself has anything to plot. False (with
  /// [hasReadingHistory] true) for someone who last read months ago.
  bool get hasWindowActivity => window.sessions > 0;

  factory LibraryStatistics.fromJson(Map<String, dynamic> json) => LibraryStatistics(
        followedTotal: (json['followed_total'] as num?)?.toInt() ?? 0,
        favorites: (json['favorites'] as num?)?.toInt() ?? 0,
        byReadingStatus: (json['by_reading_status'] as Map<String, dynamic>? ?? const {})
            .map((key, value) => MapEntry(key, (value as num?)?.toInt() ?? 0)),
        chaptersCompleted: (json['chapters_completed'] as num?)?.toInt() ?? 0,
        rangeDays: (_object(json['range'])['days'] as num?)?.toInt() ?? 30,
        totals: ReadingTotals.fromJson(_object(json['totals'])),
        window: ReadingTotals.fromJson(_object(json['window'])),
        streak: ReadingStreak.fromJson(_object(json['streak'])),
        daily: _list(json['daily'], DailyActivity.fromJson),
        byHour: _list(json['by_hour'], HourActivity.fromJson),
        bySource: _list(json['by_source'], SourceActivity.fromJson),
        bySeries: _list(json['by_series'], SeriesActivity.fromJson),
        recentSessions: _list(json['recent_sessions'], RecentSession.fromJson),
      );
}

/// The five numbers every roll-up in the payload reports, in one shape —
/// `totals` (all-time, with first/last) and `window` are the same object.
class ReadingTotals {
  const ReadingTotals({
    this.sessions = 0,
    this.pagesRead = 0,
    this.chaptersRead = 0,
    this.seriesRead = 0,
    this.secondsRead = 0,
    this.firstSessionAt,
    this.lastSessionAt,
  });

  final int sessions;
  final int pagesRead;
  final int chaptersRead;
  final int seriesRead;

  /// Wall-clock seconds, each session clamped to the backend's one-hour cap.
  /// Zero for a client that never reported elapsed time, which is why nothing
  /// on the screen leads with it.
  final int secondsRead;

  /// Only present on the all-time roll-up.
  final DateTime? firstSessionAt;
  final DateTime? lastSessionAt;

  factory ReadingTotals.fromJson(Map<String, dynamic> json) => ReadingTotals(
        sessions: (json['sessions'] as num?)?.toInt() ?? 0,
        pagesRead: (json['pages_read'] as num?)?.toInt() ?? 0,
        chaptersRead: (json['chapters_read'] as num?)?.toInt() ?? 0,
        seriesRead: (json['series_read'] as num?)?.toInt() ?? 0,
        secondsRead: (json['seconds_read'] as num?)?.toInt() ?? 0,
        firstSessionAt: _instant(json['first_session_at']),
        lastSessionAt: _instant(json['last_session_at']),
      );
}

class ReadingStreak {
  const ReadingStreak({
    this.currentDays = 0,
    this.longestDays = 0,
    this.lastActiveDate,
  });

  final int currentDays;
  final int longestDays;

  /// A local calendar day (`YYYY-MM-DD`) bucketed at the offset the client
  /// sent, so it is a date and never an instant — parsed at local midnight.
  final DateTime? lastActiveDate;

  factory ReadingStreak.fromJson(Map<String, dynamic> json) => ReadingStreak(
        currentDays: (json['current_days'] as num?)?.toInt() ?? 0,
        longestDays: (json['longest_days'] as num?)?.toInt() ?? 0,
        lastActiveDate: _localDate(json['last_active_date']),
      );
}

class DailyActivity {
  const DailyActivity({
    required this.date,
    this.sessions = 0,
    this.pagesRead = 0,
    this.chaptersRead = 0,
    this.secondsRead = 0,
  });

  /// Local calendar day (see [ReadingStreak.lastActiveDate]).
  final DateTime date;
  final int sessions;
  final int pagesRead;
  final int chaptersRead;
  final int secondsRead;

  factory DailyActivity.fromJson(Map<String, dynamic> json) => DailyActivity(
        date: _localDate(json['date']) ?? DateTime(1970),
        sessions: (json['sessions'] as num?)?.toInt() ?? 0,
        pagesRead: (json['pages_read'] as num?)?.toInt() ?? 0,
        chaptersRead: (json['chapters_read'] as num?)?.toInt() ?? 0,
        secondsRead: (json['seconds_read'] as num?)?.toInt() ?? 0,
      );
}

class HourActivity {
  const HourActivity({
    required this.hour,
    this.sessions = 0,
    this.pagesRead = 0,
    this.secondsRead = 0,
  });

  /// 0..23 in the caller's own timezone.
  final int hour;
  final int sessions;
  final int pagesRead;
  final int secondsRead;

  factory HourActivity.fromJson(Map<String, dynamic> json) => HourActivity(
        hour: (json['hour'] as num?)?.toInt() ?? 0,
        sessions: (json['sessions'] as num?)?.toInt() ?? 0,
        pagesRead: (json['pages_read'] as num?)?.toInt() ?? 0,
        secondsRead: (json['seconds_read'] as num?)?.toInt() ?? 0,
      );
}

class SourceActivity {
  const SourceActivity({
    required this.sourceId,
    required this.name,
    this.sessions = 0,
    this.pagesRead = 0,
    this.chaptersRead = 0,
    this.seriesRead = 0,
    this.secondsRead = 0,
  });

  final String sourceId;

  /// The connector's display name, falling back to the id server-side.
  final String name;
  final int sessions;
  final int pagesRead;
  final int chaptersRead;
  final int seriesRead;
  final int secondsRead;

  factory SourceActivity.fromJson(Map<String, dynamic> json) => SourceActivity(
        sourceId: json['source_id'] as String? ?? '',
        name: json['name'] as String? ?? json['source_id'] as String? ?? '',
        sessions: (json['sessions'] as num?)?.toInt() ?? 0,
        pagesRead: (json['pages_read'] as num?)?.toInt() ?? 0,
        chaptersRead: (json['chapters_read'] as num?)?.toInt() ?? 0,
        seriesRead: (json['series_read'] as num?)?.toInt() ?? 0,
        secondsRead: (json['seconds_read'] as num?)?.toInt() ?? 0,
      );
}

class SeriesActivity {
  const SeriesActivity({
    required this.sourceId,
    required this.seriesKey,
    this.title,
    this.lastReadAt,
    this.sessions = 0,
    this.pagesRead = 0,
    this.chaptersRead = 0,
    this.secondsRead = 0,
  });

  final String sourceId;

  /// Opaque connector key — passed through raw, never parsed.
  final String seriesKey;

  /// Null once the series is unfollowed: its history still counts, but the
  /// title lived on the follow row.
  final String? title;
  final DateTime? lastReadAt;
  final int sessions;
  final int pagesRead;
  final int chaptersRead;
  final int secondsRead;

  factory SeriesActivity.fromJson(Map<String, dynamic> json) => SeriesActivity(
        sourceId: json['source_id'] as String? ?? '',
        seriesKey: json['series_key'] as String? ?? '',
        title: (json['title'] as String?)?.trim(),
        lastReadAt: _instant(json['last_read_at']),
        sessions: (json['sessions'] as num?)?.toInt() ?? 0,
        pagesRead: (json['pages_read'] as num?)?.toInt() ?? 0,
        chaptersRead: (json['chapters_read'] as num?)?.toInt() ?? 0,
        secondsRead: (json['seconds_read'] as num?)?.toInt() ?? 0,
      );
}

class RecentSession {
  const RecentSession({
    required this.sourceId,
    required this.seriesKey,
    required this.chapterKey,
    this.chapterNumber,
    this.title,
    this.pagesRead = 0,
    this.secondsRead = 0,
    this.startedAt,
    this.endedAt,
  });

  final String sourceId;
  final String seriesKey;
  final String chapterKey;
  final double? chapterNumber;

  /// Null once the series is unfollowed (see [SeriesActivity.title]).
  final String? title;
  final int pagesRead;
  final int secondsRead;
  final DateTime? startedAt;
  final DateTime? endedAt;

  factory RecentSession.fromJson(Map<String, dynamic> json) => RecentSession(
        sourceId: json['source_id'] as String? ?? '',
        seriesKey: json['series_key'] as String? ?? '',
        chapterKey: json['chapter_key'] as String? ?? '',
        chapterNumber: (json['chapter_number'] as num?)?.toDouble(),
        title: (json['title'] as String?)?.trim(),
        pagesRead: (json['pages_read'] as num?)?.toInt() ?? 0,
        secondsRead: (json['seconds_read'] as num?)?.toInt() ?? 0,
        startedAt: _instant(json['started_at']),
        endedAt: _instant(json['ended_at']),
      );
}

Map<String, dynamic> _object(Object? raw) =>
    raw is Map<String, dynamic> ? raw : const {};

List<T> _list<T>(Object? raw, T Function(Map<String, dynamic>) fromJson) {
  if (raw is! List) return const [];
  return raw
      .whereType<Map<String, dynamic>>()
      .map(fromJson)
      .toList(growable: false);
}

/// An instant reported by the backend.
///
/// Every timestamp column in this project is a naive SQLite `DATETIME` holding
/// UTC (`core/time_utils.utcnow`), so it serialises with no timezone
/// designator — and `DateTime.parse` reads an offset-less string as **local**,
/// which silently shifts every "3h ago" on this screen by the device's UTC
/// offset. The designator is supplied here so callers can `.toLocal()` the way
/// they would with any other instant. Parsing is lenient: one malformed
/// timestamp must not blank the whole screen.
DateTime? _instant(Object? raw) {
  if (raw is! String || raw.isEmpty) return null;
  final zoned = raw.endsWith('Z') || _offsetSuffix.hasMatch(raw);
  return DateTime.tryParse(zoned ? raw : '${raw}Z');
}

final RegExp _offsetSuffix = RegExp(r'[+-]\d{2}:?\d{2}$');

/// A day bucket (`YYYY-MM-DD`), already bucketed at the offset this client
/// sent. It is a calendar date and not an instant, so it is parsed as-is —
/// local midnight — and must never be shifted into UTC.
DateTime? _localDate(Object? raw) =>
    raw is String && raw.isNotEmpty ? DateTime.tryParse(raw) : null;
