import 'dart:math' as math;

/// Which ordered sequence a bookmark's [Bookmark.anchorIndex] counts.
///
/// Stored on the row rather than derived from the source id: the reader that
/// captured the position is the only thing that knows for certain which
/// surface it came off, and the offline path has no sources listing to look
/// one up in.
enum BookmarkMedia {
  manga,
  novel;

  static BookmarkMedia fromWire(String? value) =>
      value == 'novel' ? BookmarkMedia.novel : BookmarkMedia.manga;

  String get wire => this == BookmarkMedia.novel ? 'novel' : 'manga';

  bool get isNovel => this == BookmarkMedia.novel;
}

/// A saved reading position — `POST /reader/bookmark`,
/// `POST /reader/bookmarks/batch`, `GET /reader/bookmarks`, and the on-device
/// `bookmarks` table, which all speak this one shape.
///
/// **The position is a generic anchor triple plus a discriminator**, not two
/// medium-specific field sets: [anchorIndex] counts pages for manga and
/// paragraphs for novels (1-based in both), [anchorFraction] is 0.0–1.0
/// *within* that unit, and [anchorTotal] is the unit count seen at capture
/// time. Different nouns, structurally identical maths — every operation over
/// them ([positionFraction], the clamp-to-nearest degradation, the sync merge,
/// the row mapping) is written once instead of twice behind an `if`.
///
/// A fraction and not pixels, deliberately: the same chapter renders at
/// different widths on the phone and on the web, so a pixel offset means two
/// different places. `chapter_progress.scroll_offset_px` is exactly that
/// mistake and is not repeated here.
///
/// **Identity is [clientId], not [id].** A bookmark made offline has no server
/// row yet — [id] is null until a flush comes back — so every local operation,
/// every outbox op and the whole merge key off the client-generated id. It is
/// opaque and is never parsed.
class Bookmark {
  const Bookmark({
    required this.clientId,
    required this.sourceId,
    required this.seriesKey,
    required this.chapterKey,
    required this.createdAt,
    required this.updatedAt,
    this.id,
    this.seriesTitle,
    this.chapterNumber,
    this.mediaType = BookmarkMedia.manga,
    this.anchorIndex = 1,
    this.anchorFraction = 0,
    this.anchorTotal = 0,
    this.snippet,
    this.anchorStale = false,
    this.note,
    this.deleted = false,
    this.deletedAt,
  });

  /// The server row id, or null for a bookmark that has never reached the
  /// server (made offline, or made while the flush was failing).
  final int? id;

  /// The sync identity: client-generated, opaque, stable for the life of the
  /// bookmark, and unique per `(user, profile)`.
  final String clientId;

  final String sourceId;
  final String seriesKey;
  final String chapterKey;

  /// Server-side enrichment off the follow row — the Bookmarks screen shows
  /// it so a row is recognisable without opening it. Null offline, where the
  /// chapter key is the honest label.
  final String? seriesTitle;

  /// Survives a source re-keying its chapters, which the opaque chapter key
  /// does not.
  final double? chapterNumber;

  final BookmarkMedia mediaType;

  /// 1-based page (manga) or paragraph (novel).
  final int anchorIndex;

  /// 0.0–1.0 within the unit [anchorIndex] names.
  final double anchorFraction;

  /// Units in the chapter as the capturing client saw them. `0` means the
  /// client never recorded one — a snapshot, never authoritative.
  final int anchorTotal;

  /// The prose at the bookmarked point, for novels. What makes a bookmark in
  /// a wall of text recognisable at a glance; null for manga and for a novel
  /// chapter whose text is not cached anywhere this client can read.
  final String? snippet;

  /// True when the recorded unit no longer exists and the nearest valid one
  /// was used. False means "not known to be stale", never "verified fresh".
  final bool anchorStale;

  final String? note;

  /// A tombstone, not a removal. Deletes have to be *learnable* by a device
  /// that was offline when one happened, and a row that simply vanished from
  /// a listing is indistinguishable from one that was never pulled.
  final bool deleted;

  final DateTime createdAt;

  /// Last-write-wins clock and the delta cursor. UTC.
  final DateTime updatedAt;

  final DateTime? deletedAt;

  /// How far through the CHAPTER this sits, or null when [anchorTotal] is 0.
  ///
  /// Null and not 0.0 on purpose: a client that recorded no unit count has
  /// said nothing about where in the chapter it was, and "0% of the chapter"
  /// would be a fabrication — old page-only bookmarks migrated from before
  /// this design are exactly that case.
  ///
  /// Identical arithmetic to `services.bookmark_service.position_fraction`,
  /// including the 4-decimal rounding, so a bookmark read off the device and
  /// the same bookmark read off the server never disagree by a rounding step.
  double? get positionFraction =>
      bookmarkPositionFraction(anchorIndex, anchorFraction, anchorTotal);

  /// [positionFraction] as whole percent, or null when it is unknown.
  int? get positionPercent =>
      bookmarkPositionPercent(anchorIndex, anchorFraction, anchorTotal);

  Bookmark copyWith({
    int? id,
    String? seriesTitle,
    String? snippet,
    bool? anchorStale,
    String? note,
    bool? deleted,
    DateTime? updatedAt,
    DateTime? deletedAt,
  }) =>
      Bookmark(
        id: id ?? this.id,
        clientId: clientId,
        sourceId: sourceId,
        seriesKey: seriesKey,
        chapterKey: chapterKey,
        seriesTitle: seriesTitle ?? this.seriesTitle,
        chapterNumber: chapterNumber,
        mediaType: mediaType,
        anchorIndex: anchorIndex,
        anchorFraction: anchorFraction,
        anchorTotal: anchorTotal,
        snippet: snippet ?? this.snippet,
        anchorStale: anchorStale ?? this.anchorStale,
        note: note ?? this.note,
        deleted: deleted ?? this.deleted,
        createdAt: createdAt,
        updatedAt: updatedAt ?? this.updatedAt,
        deletedAt: deletedAt ?? this.deletedAt,
      );

  /// The identity of the chapter this bookmark points into.
  ({String sourceId, String seriesKey, String chapterKey}) get chapterId =>
      (sourceId: sourceId, seriesKey: seriesKey, chapterKey: chapterKey);

  factory Bookmark.fromJson(Map<String, dynamic> json) {
    final created = bookmarkInstant(json['created_at']);
    final updated = bookmarkInstant(json['updated_at']);
    return Bookmark(
      id: (json['id'] as num?)?.toInt(),
      // A server old enough to answer without a client id still has to
      // round-trip through a device row, whose primary key it is; the server
      // row id is the only identity such a response carries.
      clientId: ((json['client_id'] as String?)?.trim().isNotEmpty ?? false)
          ? json['client_id'] as String
          : 'srv-${json['id']}',
      sourceId: json['source_id'] as String? ?? '',
      seriesKey: json['series_key'] as String? ?? '',
      chapterKey: json['chapter_key'] as String? ?? '',
      seriesTitle: json['series_title'] as String?,
      chapterNumber: (json['chapter_number'] as num?)?.toDouble(),
      mediaType: BookmarkMedia.fromWire(json['media_type'] as String?),
      // `page` is the deprecated mirror an older server sends alone.
      anchorIndex: (json['anchor_index'] as num?)?.toInt() ??
          (json['page'] as num?)?.toInt() ??
          1,
      anchorFraction: (json['anchor_fraction'] as num?)?.toDouble() ?? 0,
      anchorTotal: (json['anchor_total'] as num?)?.toInt() ?? 0,
      snippet: json['snippet'] as String?,
      anchorStale: json['anchor_stale'] as bool? ?? false,
      note: json['note'] as String?,
      deleted: json['deleted'] as bool? ?? false,
      createdAt: created ?? updated ?? _epoch,
      updatedAt: updated ?? created ?? _epoch,
      deletedAt: bookmarkInstant(json['deleted_at']),
    );
  }

  /// This bookmark as one item of `POST /reader/bookmarks/batch`.
  ///
  /// [op] is `"upsert"` or `"delete"`. `updated_at` is the DEVICE's clock, not
  /// the server's: it is what decides last-write-wins between two devices
  /// editing the same bookmark, and a flush that happens hours after the
  /// capture must still be ordered by when the reader actually acted.
  Map<String, dynamic> toOpJson(String op) => {
        'op': op,
        'client_id': clientId,
        'source_id': sourceId,
        'series_key': seriesKey,
        'chapter_key': chapterKey,
        if (chapterNumber != null) 'chapter_number': chapterNumber,
        'media_type': mediaType.wire,
        'anchor_index': anchorIndex,
        'anchor_fraction': anchorFraction,
        'anchor_total': anchorTotal,
        if (note != null) 'note': note,
        'updated_at': updatedAt.toUtc().toIso8601String(),
      };

  /// A fresh client id.
  ///
  /// Time-ordered prefix plus randomness, rather than a uuid package: the id
  /// is opaque to both sides and never parsed, the ordering makes an outbox
  /// dump readable, and the app's dependency set is fixed. 64 chars is the
  /// server's limit; this is 25 or so.
  static String mintClientId() {
    final stamp =
        DateTime.now().toUtc().microsecondsSinceEpoch.toRadixString(36);
    final noise = _random.nextInt(1 << 32).toRadixString(36).padLeft(7, '0');
    return 'mm$stamp$noise';
  }

  static final math.Random _random = math.Random.secure();
}

final DateTime _epoch = DateTime.fromMillisecondsSinceEpoch(0, isUtc: true);

/// The two ops `POST /reader/bookmarks/batch` understands.
const String kBookmarkOpUpsert = 'upsert';
const String kBookmarkOpDelete = 'delete';

/// One item of an offline flush: what to do, and to which bookmark.
///
/// A delete still carries the whole body even though the server re-identifies
/// by [Bookmark.clientId] alone — the outbox row is also the only record of
/// what was deleted, and a payload that dropped the identity could not be read
/// back for a diagnostic.
class BookmarkOp {
  const BookmarkOp({required this.op, required this.bookmark});

  final String op;
  final Bookmark bookmark;

  bool get isDelete => op == kBookmarkOpDelete;

  Map<String, dynamic> toJson() => bookmark.toOpJson(op);

  factory BookmarkOp.fromJson(Map<String, dynamic> json) => BookmarkOp(
        op: json['op'] as String? ?? kBookmarkOpUpsert,
        bookmark: Bookmark.fromJson(json),
      );
}

/// What `POST /reader/bookmarks/batch` reports back.
///
/// [serverIds] is the part that matters to the device: `client_id -> id` for
/// every item the server actually holds a row for, which is how a bookmark
/// created on a plane learns its server id once it lands.
///
/// A per-item status is never fatal here for the same reason it is not on the
/// server: an outbox whose whole flush is refused over one bad row retries it
/// forever and never drains. [rejected] is counted and the rows are cleared
/// regardless — a rejected op is *settled*, not pending.
class BookmarkSyncResult {
  const BookmarkSyncResult({
    required this.received,
    required this.created,
    required this.updated,
    required this.tombstoned,
    required this.rejected,
    required this.serverIds,
  });

  final int received;
  final int created;
  final int updated;
  final int tombstoned;
  final int rejected;
  final Map<String, int> serverIds;

  factory BookmarkSyncResult.fromJson(Map<String, dynamic> json) {
    final serverIds = <String, int>{};
    for (final raw in (json['items'] as List<dynamic>? ?? const [])) {
      if (raw is! Map) continue;
      final clientId = raw['client_id'];
      final body = raw['bookmark'];
      if (clientId is! String || body is! Map) continue;
      final id = (body['id'] as num?)?.toInt();
      if (id != null) serverIds[clientId] = id;
    }
    return BookmarkSyncResult(
      received: (json['received'] as num?)?.toInt() ?? 0,
      created: (json['created'] as num?)?.toInt() ?? 0,
      updated: (json['updated'] as num?)?.toInt() ?? 0,
      tombstoned: (json['tombstoned'] as num?)?.toInt() ?? 0,
      rejected: (json['rejected'] as num?)?.toInt() ?? 0,
      serverIds: serverIds,
    );
  }
}

/// How far through a chapter an anchor sits, or null when the unit count is
/// unknown.
///
/// Null and not 0.0 when [anchorTotal] is 0: a client that recorded no unit
/// count has said nothing about where in the chapter it was, and "0% of the
/// chapter" would be a fabrication.
///
/// A free function as well as a getter on [Bookmark] because the reader needs
/// the same number for a position it has just measured and not yet stored —
/// and two implementations of one formula is how the reader's snackbar and
/// the Bookmarks screen come to disagree about the same bookmark.
///
/// Byte-identical to `services.bookmark_service.position_fraction`, rounding
/// included.
double? bookmarkPositionFraction(
  int anchorIndex,
  double anchorFraction,
  int anchorTotal,
) {
  if (anchorTotal <= 0) return null;
  final index = anchorIndex.clamp(1, anchorTotal);
  final raw = (index - 1 + clampBookmarkFraction(anchorFraction)) / anchorTotal;
  return (raw.clamp(0.0, 1.0) * 10000).round() / 10000;
}

/// [bookmarkPositionFraction] as whole percent.
int? bookmarkPositionPercent(
  int anchorIndex,
  double anchorFraction,
  int anchorTotal,
) {
  final fraction =
      bookmarkPositionFraction(anchorIndex, anchorFraction, anchorTotal);
  return fraction == null ? null : (fraction * 100).round();
}

/// A fraction, forced into 0.0–1.0. Garbage and NaN read as 0.0 — the same
/// coercion `services.bookmark_service.clamp_fraction` applies, so a value
/// that survives here survives there.
double clampBookmarkFraction(num? value) {
  final number = (value ?? 0).toDouble();
  if (number.isNaN) return 0;
  return number.clamp(0.0, 1.0);
}

/// An instant reported by the backend.
///
/// Every timestamp column in this project is a naive SQLite `DATETIME` holding
/// UTC (`core/time_utils.utcnow`), so it serialises with no timezone
/// designator — and `DateTime.parse` reads an offset-less string as **local**.
/// For a display timestamp that is a cosmetic shift; for [Bookmark.updatedAt]
/// it is the last-write-wins comparison itself, so a device in +05:30 would
/// consider every server row five and a half hours stale. The designator is
/// supplied here, once.
DateTime? bookmarkInstant(Object? raw) {
  if (raw is! String || raw.isEmpty) return null;
  final zoned = raw.endsWith('Z') || _offsetSuffix.hasMatch(raw);
  return DateTime.tryParse(zoned ? raw : '${raw}Z')?.toUtc();
}

final RegExp _offsetSuffix = RegExp(r'[+-]\d{2}:?\d{2}$');
