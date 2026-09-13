/// An instant reported by the backend.
///
/// Every timestamp column in this project is a naive SQLite `DATETIME` holding
/// UTC (`core/time_utils.utcnow`), so it serialises with no timezone
/// designator — and `DateTime.parse` reads an offset-less string as **local**,
/// which silently shifts every server timestamp by the device's UTC offset
/// (+05:30 turns a chapter read a minute ago into one read five and a half
/// hours from now, and a session in use right now into one last seen five and
/// a half hours ago). A screen's `.toLocal()` cannot undo it either: on a
/// DateTime that already claims to be local it is a no-op.
///
/// For a display timestamp that shift is cosmetic; for `Bookmark.updatedAt` it
/// is the last-write-wins comparison itself, so a device in +05:30 would
/// consider every server row five and a half hours stale. The designator is
/// supplied here, once, for every model that parses a server timestamp — three
/// separate copies of this function is how they came to disagree in the first
/// place.
///
/// Parsing is lenient: null on malformed input rather than a throw, because
/// one bad row must not blank the screen the user came to read. Callers that
/// need a non-null instant supply their own floor.
DateTime? serverInstant(Object? raw) {
  if (raw is! String) return null;
  final value = raw.trim();
  if (value.isEmpty) return null;
  // A date with no time is ALREADY read as UTC midnight, and appending the
  // designator to one produces a string Dart cannot parse at all
  // ('2026-09-08Z' -> null), so a bare `YYYY-MM-DD` would come back null and
  // the caller would see "no date" for a date the source did publish. Chapter
  // lists are full of them. This mirrors the HAS_TIME guard in the web's
  // `lib/utc-time.ts`, which is the contract this function is meant to share.
  final needsDesignator = _timeComponent.hasMatch(value) &&
      !value.endsWith('Z') &&
      !value.endsWith('z') &&
      !_offsetSuffix.hasMatch(value);
  return DateTime.tryParse(needsDesignator ? '${value}Z' : value)?.toUtc();
}

final RegExp _offsetSuffix = RegExp(r'[+-]\d{2}:?\d{2}$');
final RegExp _timeComponent = RegExp(r'\d{2}:\d{2}');
