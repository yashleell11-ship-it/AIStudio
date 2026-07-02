import 'package:shared_preferences/shared_preferences.dart';

const _scrollPrefix = 'aistudio-reader-scroll:';

/// Per-chapter scroll position keyed by an opaque string.
///
/// The local library reader passes the integer chapter id; the online source
/// reader passes a composite key (``sourceId:seriesId:chapterId``) so each
/// remote chapter keeps its own position without colliding with local storage.
double? readReaderScrollPositionByKey(SharedPreferences prefs, String key) {
  final raw = prefs.getDouble('$_scrollPrefix$key');
  if (raw == null || raw.isNaN || raw.isInfinite || raw < 0) return null;
  return raw;
}

Future<void> writeReaderScrollPositionByKey(
  SharedPreferences prefs,
  String key,
  double scrollOffset,
) =>
    prefs.setDouble('$_scrollPrefix$key', scrollOffset.roundToDouble());

double? readReaderScrollPosition(SharedPreferences prefs, int chapterId) =>
    readReaderScrollPositionByKey(prefs, chapterId.toString());

Future<void> writeReaderScrollPosition(
  SharedPreferences prefs,
  int chapterId,
  double scrollOffset,
) =>
    writeReaderScrollPositionByKey(prefs, chapterId.toString(), scrollOffset);
