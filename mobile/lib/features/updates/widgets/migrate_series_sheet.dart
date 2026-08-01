import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/profiles/providers/profile_scope.dart';
import 'package:manhwamaniacs/features/sources/providers/source_progress_provider.dart';
import 'package:manhwamaniacs/features/updates/models/series_tracker.dart';
import 'package:manhwamaniacs/features/updates/models/source_migration.dart';
import 'package:manhwamaniacs/features/updates/providers/updates_provider.dart';
import 'package:manhwamaniacs/features/updates/utils/migration_plan_view.dart';
import 'package:manhwamaniacs/features/updates/utils/migration_ranking.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';
import 'package:manhwamaniacs/shared/widgets/empty_state.dart';
import 'package:manhwamaniacs/shared/widgets/series_cover_image.dart';

/// Move a followed series to another source, keeping reading progress.
///
/// Mirrors the web's `MigrateSeriesDialog`. Three stages in one sheet:
/// pick a candidate, review the plan the server computed, confirm. The server
/// treats preview and commit identically apart from a `dry_run` flag, so the
/// map shown at stage two is built exactly like the one applied at stage three.
Future<void> showMigrateSeriesSheet(
  BuildContext context, {
  required SeriesTracker tracker,
}) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    backgroundColor: AppColors.surface,
    constraints: const BoxConstraints(maxWidth: 640),
    builder: (_) => MigrateSeriesSheet(tracker: tracker),
  );
}

class MigrateSeriesSheet extends ConsumerStatefulWidget {
  const MigrateSeriesSheet({required this.tracker, super.key});

  final SeriesTracker tracker;

  @override
  ConsumerState<MigrateSeriesSheet> createState() => _MigrateSeriesSheetState();
}

class _MigrateSeriesSheetState extends ConsumerState<MigrateSeriesSheet> {
  final _offsetController = TextEditingController();

  MigrationCandidateList? _candidates;
  MigrationCandidate? _chosen;
  MigrationPlan? _plan;

  bool _loading = true;
  bool _busy = false;
  String? _error;
  /// Set when the target is already followed; the retry opts into merging.
  int? _conflictTrackerId;

  @override
  void initState() {
    super.initState();
    _loadCandidates();
  }

  @override
  void dispose() {
    _offsetController.dispose();
    super.dispose();
  }

  Future<void> _loadCandidates() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    final result = await ref
        .read(sourceMigrationRepositoryProvider)
        .candidates(widget.tracker.id);
    if (!mounted) return;

    switch (result) {
      case Ok(:final value):
        setState(() {
          _candidates = value;
          _loading = false;
        });
      case Err(:final error):
        if (recoverFromProfileScopeError(ref, error)) return;
        setState(() {
          _error = error.userMessage;
          _loading = false;
        });
    }
  }

  /// Ask the server for the plan without writing anything.
  Future<void> _preview(MigrationCandidate candidate) async {
    final offset = parseChapterOffset(_offsetController.text);
    if (offset == null) {
      // Garbage in the offset field must not silently become 0 — that would
      // preview a different migration than the one the reader typed.
      setState(() => _error = 'Chapter offset must be a number.');
      return;
    }
    if (_busy) return;

    setState(() {
      _busy = true;
      _error = null;
      _chosen = candidate;
    });

    final result = await ref.read(sourceMigrationRepositoryProvider).migrate(
          widget.tracker.id,
          targetSource: candidate.source,
          targetSeriesId: candidate.seriesId,
          targetSeriesTitle: candidate.title,
          chapterOffset: offset,
        );
    if (!mounted) return;

    switch (result) {
      case Ok(:final value):
        setState(() {
          _plan = value;
          _busy = false;
        });
      case Err(:final error):
        if (recoverFromProfileScopeError(ref, error)) return;
        setState(() {
          _busy = false;
          _chosen = null;
          _error = isTargetUnreachable(error)
              ? "Could not read that source's chapter list. Try another."
              : error.userMessage;
        });
    }
  }

  /// Commit the plan the reader just saw, pinned by its hash.
  Future<void> _commit({bool merge = false}) async {
    final plan = _plan;
    final candidate = _chosen;
    if (plan == null || candidate == null || _busy) return;

    setState(() {
      _busy = true;
      _error = null;
    });

    final messenger = ScaffoldMessenger.of(context);
    final navigator = Navigator.of(context);
    final result = await ref.read(sourceMigrationRepositoryProvider).migrate(
          widget.tracker.id,
          targetSource: candidate.source,
          targetSeriesId: candidate.seriesId,
          targetSeriesTitle: candidate.title,
          chapterOffset: parseChapterOffset(_offsetController.text) ?? 0,
          dryRun: false,
          merge: merge,
          // Pins the commit to the map that was displayed. If the target gained
          // chapters since the preview the server refuses rather than applying
          // a mapping nobody saw.
          expectedChapterMapHash: plan.chapterMapHash,
        );
    if (!mounted) return;

    switch (result) {
      case Ok(:final value):
        await _afterApplied(value);
        if (!mounted) return;
        navigator.pop();
        messenger.showSnackBar(
          SnackBar(content: Text('Moved to ${candidate.displayName}.')),
        );
      case Err(:final error):
        // The target's chapter list moved under us. The server hands back a
        // freshly computed plan; show that rather than re-running the preview,
        // and never retry with the hash stripped.
        final stale = stalePreviewFromError(error);
        if (stale != null) {
          setState(() {
            _plan = stale;
            _busy = false;
            _error = "The target's chapter list changed. Review it again.";
          });
          return;
        }

        final conflict = migrationConflictTrackerId(error);
        if (conflict != null) {
          setState(() {
            _busy = false;
            _conflictTrackerId = conflict;
            _error = 'You already follow this series on that source.';
          });
          return;
        }

        if (recoverFromProfileScopeError(ref, error)) return;
        setState(() {
          _busy = false;
          _error = error.userMessage;
        });
    }
  }

  /// Local work that only makes sense once the server actually applied it.
  Future<void> _afterApplied(MigrationPlan plan) async {
    // Progress first: online reading position for a remote series lives only
    // in the on-device store, so refreshing trackers before remapping would
    // briefly show the new source with the reader's place lost.
    await ref.read(sourceProgressProvider.notifier).remapSeriesProgress(
          fromSourceId: plan.fromSource,
          fromSeriesId: plan.fromSeriesId,
          toSourceId: plan.toSource,
          toSeriesId: plan.toSeriesId,
          carriedChapterIds: plan.carriedChapterIds,
        );
    await ref.read(updatesProvider.notifier).refresh();
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      top: false,
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxHeight: MediaQuery.sizeOf(context).height * 0.85,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(
                AppSpacing.xl2,
                0,
                AppSpacing.xl2,
                AppSpacing.md,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Move to another source', style: AppTypography.h2),
                  const SizedBox(height: AppSpacing.xs),
                  Text(
                    widget.tracker.seriesTitle,
                    style: AppTypography.body.copyWith(color: AppColors.muted),
                  ),
                ],
              ),
            ),
            Flexible(child: SingleChildScrollView(child: _body())),
          ],
        ),
      ),
    );
  }

  Widget _body() {
    if (_loading) {
      return const Padding(
        padding: EdgeInsets.all(AppSpacing.xl3),
        child: Center(child: CircularProgressIndicator()),
      );
    }

    final plan = _plan;
    if (plan != null) return _planView(plan);
    return _candidateList();
  }

  // ── stage 1: pick a source ────────────────────────────────────────────────

  Widget _candidateList() {
    final list = _candidates;
    if (list == null || list.candidates.isEmpty) {
      return Padding(
        padding: const EdgeInsets.all(AppSpacing.xl2),
        child: Column(
          children: [
            const EmptyState(
              icon: Icons.travel_explore_outlined,
              message: 'No other source has this series',
              subtitle: 'Nothing to move it to right now.',
            ),
            if (_error != null) ...[
              const SizedBox(height: AppSpacing.md),
              _errorText(_error!),
            ],
          ],
        ),
      );
    }

    // Server order is preserved verbatim: it already demotes unhealthy
    // connectors, and re-sorting here would undo that.
    final ranked = rankMigrationCandidates(
      list.candidates,
      followedTitle: widget.tracker.seriesTitle,
      knownChapterCount: widget.tracker.knownChapterCount,
    );

    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.xl2,
        0,
        AppSpacing.xl2,
        AppSpacing.xl2,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (_error != null) ...[
            _errorText(_error!),
            const SizedBox(height: AppSpacing.md),
          ],
          _offsetField(),
          const SizedBox(height: AppSpacing.lg),
          ...ranked.map(_candidateTile),
          if (list.sourcesFailed > 0) ...[
            const SizedBox(height: AppSpacing.md),
            Text(
              // Most of the registry is dead connectors; a large number here is
              // routine and is not an error worth alarming anyone about.
              'Searched ${list.sourcesQueried} sources, '
              '${list.sourcesFailed} did not answer.',
              style: AppTypography.caption.copyWith(color: AppColors.muted),
            ),
          ],
        ],
      ),
    );
  }

  Widget _offsetField() {
    return TextField(
      controller: _offsetController,
      keyboardType: const TextInputType.numberWithOptions(
        decimal: true,
        signed: true,
      ),
      decoration: const InputDecoration(
        labelText: 'Chapter offset',
        helperText: 'For targets that restart numbering per season.',
        isDense: true,
      ),
    );
  }

  Widget _candidateTile(RankedMigrationCandidate ranked) {
    final candidate = ranked.candidate;
    final busy = _busy && _chosen?.seriesId == candidate.seriesId;

    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Material(
        type: MaterialType.transparency,
        child: ListTile(
          contentPadding: EdgeInsets.zero,
          leading: SizedBox(
            width: 44,
            height: 60,
            child: candidate.coverUrl == null
                ? const ColoredBox(color: AppColors.surface2)
                // Already an absolute backend-served URL — no base resolution.
                : SeriesCoverImage(url: candidate.coverUrl!),
          ),
          title: Text(candidate.title, style: AppTypography.labelLg),
          subtitle: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                candidate.displayName,
                style: AppTypography.bodySm.copyWith(color: AppColors.muted),
              ),
              Text(
                ranked.titleMatch.label,
                style: AppTypography.caption.copyWith(
                  color: ranked.losesTail
                      ? AppColors.warning
                      : AppColors.muted,
                ),
              ),
              if (ranked.losesTail)
                Text(
                  '${ranked.chapterShortfall} fewer chapters than you follow',
                  style: AppTypography.caption
                      .copyWith(color: AppColors.warning),
                ),
            ],
          ),
          trailing: busy
              ? const SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.chevron_right),
          onTap: _busy ? null : () => _preview(candidate),
        ),
      ),
    );
  }

  // ── stage 2/3: review the plan, then confirm ──────────────────────────────

  Widget _planView(MigrationPlan plan) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.xl2,
        0,
        AppSpacing.xl2,
        AppSpacing.xl2,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (_error != null) ...[
            _errorText(_error!),
            const SizedBox(height: AppSpacing.md),
          ],
          Text(migrationSummary(plan.counts), style: AppTypography.body),
          const SizedBox(height: AppSpacing.sm),
          Text(
            oldCatalogLabel(plan.oldCatalog),
            style: AppTypography.labelSm.copyWith(color: AppColors.muted),
          ),
          Text(
            oldCatalogDetail(plan.oldCatalog, plan.fromSource),
            style: AppTypography.caption.copyWith(color: AppColors.muted),
          ),

          // Server-authored prose — rendered verbatim rather than reworded,
          // so both clients say the same thing about the same plan.
          ...plan.warnings.map(
            (warning) => Padding(
              padding: const EdgeInsets.only(top: AppSpacing.sm),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(
                    Icons.warning_amber_outlined,
                    size: 16,
                    color: AppColors.warning,
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: Text(
                      warning,
                      style: AppTypography.bodySm
                          .copyWith(color: AppColors.warning),
                    ),
                  ),
                ],
              ),
            ),
          ),

          if (plan.siblingTrackers.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.sm),
            Text(
              'A downloaded copy on the old source stays where it is.',
              style: AppTypography.caption.copyWith(color: AppColors.muted),
            ),
          ],

          const SizedBox(height: AppSpacing.lg),
          Row(
            children: [
              TextButton(
                onPressed: _busy
                    ? null
                    : () => setState(() {
                          _plan = null;
                          _chosen = null;
                          _error = null;
                          _conflictTrackerId = null;
                        }),
                child: const Text('Back'),
              ),
              const Spacer(),
              FilledButton(
                onPressed: _busy
                    ? null
                    : () => _commit(merge: _conflictTrackerId != null),
                child: Text(
                  _busy
                      ? 'Working…'
                      : _conflictTrackerId != null
                          ? 'Merge anyway'
                          : 'Move series',
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _errorText(String message) => Text(
        message,
        style: AppTypography.body.copyWith(color: AppColors.danger),
      );
}
