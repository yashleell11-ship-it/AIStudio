import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/updates/models/source_migration.dart';

/// Pure helpers for reading a migration plan and the two refusals the commit
/// can come back with.
///
/// Kept out of the sheet so the refusal handling is unit-testable: both are 409s
/// that must NOT be retried blindly, and getting either wrong loses the reader's
/// place. Mirrors `frontend/src/features/updates/migration.ts` so the phone and
/// the browser tell the owner the same story.

/// One-line description of what a plan would carry over.
///
/// Wording is shared verbatim with the web client
/// (`frontend/src/features/updates/migration.ts:58-63`) — the same follow read
/// on two devices should not describe the same move two ways.
String migrationSummary(MigrationCounts counts) {
  final base = '${counts.matched} of ${counts.oldTotal} chapters map onto '
      "the target's ${counts.newTotal}";
  return counts.dropped > 0
      ? '$base · ${counts.dropped} cannot be carried over'
      : '$base · nothing is left behind';
}

/// Whether the source being left could be read, named plainly.
///
/// The server's `warnings` explain this in prose; this is the crisp label that
/// goes next to it, so "the old source is dead" is a thing the screen SAYS
/// rather than something the owner has to infer from a paragraph.
String oldCatalogLabel(OldCatalogState state) => switch (state) {
      OldCatalogState.ok => 'Old source: readable',
      OldCatalogState.cached => 'Old source: cached list',
      OldCatalogState.unavailable => 'Old source: unavailable',
    };

/// One sentence naming what [state] means for the reader's progress.
String oldCatalogDetail(OldCatalogState state, String oldSource) =>
    switch (state) {
      OldCatalogState.ok =>
        '$oldSource answered, so the mapping below is built from its live '
            'chapter list.',
      OldCatalogState.cached =>
        '$oldSource did not answer. The mapping below uses the chapter list '
            'recorded at the last successful update check, so anything added '
            'there since is not represented.',
      OldCatalogState.unavailable =>
        '$oldSource did not answer and no chapter list was ever recorded, so '
            'no reading progress can be remapped. The follow still moves; your '
            'existing progress is left untouched.',
    };

/// Parse the chapter-offset field.
///
/// Returns null for input that is not a finite number so the caller can refuse
/// to preview rather than silently send 0 — an offset of 0 and a typo produce
/// very different maps. An empty field genuinely means no offset.
double? parseChapterOffset(String raw) {
  final trimmed = raw.trim();
  if (trimmed.isEmpty) return 0;
  final value = double.tryParse(trimmed);
  if (value == null || !value.isFinite) return null;
  return value;
}

Map<String, dynamic>? _details(AppError error) {
  if (error is! ApiError) return null;
  final details = error.details;
  return details is Map<String, dynamic> ? details : null;
}

/// The id of the follow that already points at the chosen target, or null when
/// that is not why the commit failed.
///
/// The server refuses by default rather than merging (`update_service.py:874-898`):
/// the two follows can carry different notify / auto-download / interval
/// settings and different known chapters, and silently picking a winner is what
/// later shows up as "it stopped notifying me". Merging is an explicit opt-in.
int? migrationConflictTrackerId(AppError error) {
  if (error is! ApiError || error.code != 'tracker_target_already_followed') {
    return null;
  }
  final existing = _details(error)?['existing_tracker_id'];
  return existing is int ? existing : null;
}

/// The freshly recomputed plan carried by a `migration_stale` refusal, or null.
///
/// The target gained or lost chapters between preview and confirm, so the map
/// the user approved is no longer the map that would be applied. The server
/// hands back the new one (`update_service.py:863-872`) instead of applying
/// something nobody saw — so the caller must re-render it and ask again, never
/// retry with the stale hash stripped.
MigrationPlan? stalePreviewFromError(AppError error) {
  if (error is! ApiError || error.code != 'migration_stale') return null;
  final preview = _details(error)?['preview'];
  if (preview is! Map<String, dynamic>) return null;
  if (preview['chapter_map_hash'] is! String) return null;
  try {
    return MigrationPlan.fromJson(preview);
  } catch (_) {
    // A malformed preview is not worth crashing the sheet over; the caller
    // falls back to re-previewing from scratch.
    return null;
  }
}

/// True when the target's chapter list could not be read at all (502).
/// Distinct from a dead *old* source, which is recoverable and expected.
bool isTargetUnreachable(AppError error) =>
    error is ApiError && error.code == 'migration_target_unreachable';
