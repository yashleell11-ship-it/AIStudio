import 'package:shared_preferences/shared_preferences.dart';

const _scrollPrefix = 'aistudio-reader-scroll:';

String _storageKey(int chapterId) => '$_scrollPrefix$chapterId';

double? readReaderScrollPosition(SharedPreferences prefs, int chapterId) {
  final raw = prefs.getDouble(_storageKey(chapterId));
  if (raw == null || raw.isNaN || raw.isInfinite || raw < 0) return null;
  return raw;
}

Future<void> writeReaderScrollPosition(
  SharedPreferences prefs,
  int chapterId,
  double scrollOffset,
) =>
    prefs.setDouble(_storageKey(chapterId), scrollOffset.roundToDouble());
