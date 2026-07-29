import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/updates/models/source_migration.dart';

/// The two source-migration endpoints, kept separate from [UpdatesRepository].
///
/// Same split as `library` / `global_search`: the updates repository backs an
/// always-loaded provider with a small CRUD surface, while these two are slow,
/// modal-only calls with their own models. Keeping them apart means the
/// migration sheet's fakes do not have to stub notification and tracker CRUD,
/// and the tracker CRUD fakes do not have to stub migration.
abstract interface class SourceMigrationRepository {
  /// Candidate targets for repointing [trackerId] at another source.
  ///
  /// Backed by the federated fan-out across every browsable connector, so this
  /// is SLOW (tens of seconds is normal) and inherits the fan-out's
  /// partial-failure reporting: a large `sourcesFailed` is routine.
  ///
  /// [query] defaults server-side to the followed title.
  Future<Result<MigrationCandidateList>> candidates(
    int trackerId, {
    String? query,
    int perPage = 10,
  });

  /// Preview ([dryRun] true, the default) or perform a migration.
  ///
  /// Both return the identical [MigrationPlan] shape from the same server code
  /// path; `applied` says which happened. Pass the preceding preview's
  /// [expectedChapterMapHash] on commit so a target whose chapter list changed
  /// in between is refused (409 `migration_stale`) rather than applying a map
  /// the user never saw. [merge] is only meaningful after a 409
  /// `tracker_target_already_followed`.
  Future<Result<MigrationPlan>> migrate(
    int trackerId, {
    required String targetSource,
    required String targetSeriesId,
    String? targetSeriesTitle,
    double chapterOffset = 0,
    bool dryRun = true,
    bool merge = false,
    String? expectedChapterMapHash,
  });
}
