/// The opaque `(sourceId, seriesKey, chapterKey)` triple that identifies a
/// chapter everywhere in the source-native client (manifest, reader,
/// progress, and — from 1c-M3 — the on-device store). Never parsed or split;
/// see `docs/superpowers/specs/2026-09-03-mobile-source-native-design.md` §1.
typedef ChapterIdentity = ({
  String sourceId,
  String seriesKey,
  String chapterKey,
});

/// A series identity, for series-level operations (queueing every chapter,
/// pin toggles, per-series storage totals).
typedef SeriesIdentity = ({String sourceId, String seriesKey});
