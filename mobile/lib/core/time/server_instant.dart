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
  if (raw is! String || raw.isEmpty) return null;
  final zoned = raw.endsWith('Z') || _offsetSuffix.hasMatch(raw);
  return DateTime.tryParse(zoned ? raw : '${raw}Z')?.toUtc();
}

final RegExp _offsetSuffix = RegExp(r'[+-]\d{2}:?\d{2}$');
