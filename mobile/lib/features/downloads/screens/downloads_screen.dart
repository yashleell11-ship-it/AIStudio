import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/features/downloads/models/download_chapter_state.dart';
import 'package:manhwamaniacs/features/downloads/models/downloaded_series_group.dart';
import 'package:manhwamaniacs/features/downloads/models/saved_chapter.dart';
import 'package:manhwamaniacs/features/downloads/providers/active_download_queue_provider.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloaded_series_provider.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/widgets/active_downloads_panel.dart';
import 'package:manhwamaniacs/features/downloads/widgets/downloads_storage_card.dart';
import 'package:manhwamaniacs/features/downloads/widgets/export_downloads_action.dart';
import 'package:manhwamaniacs/features/ocr/widgets/ocr_chapter_action.dart';
import 'package:manhwamaniacs/features/ocr/widgets/ocr_run_banner.dart';
import 'package:manhwamaniacs/features/sources/utils/chapter_label.dart';
import 'package:manhwamaniacs/shared/widgets/empty_state.dart';
import 'package:manhwamaniacs/shared/widgets/glass_card.dart';

/// The downloads area: a top-level tab, not a row buried in More.
///
/// It answers three questions the owner asked in this order — *is anything
/// happening?* (the live queue panel), *what is on my phone and what is it
/// costing me?* (the saved list, largest series first), and *where did it
/// go?* (the note below the queue plus Save to Files).
///
/// Two tabs rather than one long scroll: Chapters is the thing you open the
/// area for, Storage is the thing you open it for once a month. Storage holds
/// the very same [DownloadsStorageCard] that Settings → Storage does — the
/// widget is embedded twice, never forked, so the cap, the retention interval
/// and Free up space have exactly one implementation and one set of
/// providers behind them.
class DownloadsScreen extends ConsumerStatefulWidget {
  const DownloadsScreen({super.key});

  @override
  ConsumerState<DownloadsScreen> createState() => _DownloadsScreenState();
}

class _DownloadsScreenState extends ConsumerState<DownloadsScreen>
    with SingleTickerProviderStateMixin {
  /// Built in [initState], not lazily: the no-profile branch below never
  /// renders the TabBar, and a `late final` initialiser would then run for
  /// the first time inside [dispose] — where looking up the TickerMode
  /// ancestor is already unsafe.
  late final TabController _tabs;

  /// The per-chapter queue list is collapsed by default: the panel's summary
  /// answers "is it working" on its own, and a 200-chapter queue would bury
  /// the library underneath it.
  var _queueExpanded = false;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scopeId = ref.watch(activeDownloadsScopeIdProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Downloads'),
        bottom: scopeId == null
            ? null
            : TabBar(
                controller: _tabs,
                labelColor: AppColors.primary,
                unselectedLabelColor: AppColors.muted,
                indicatorColor: AppColors.primary,
                tabs: const [
                  Tab(text: 'Chapters'),
                  Tab(text: 'Storage'),
                ],
              ),
      ),
      body: scopeId == null
          ? const EmptyState(
              icon: Icons.person_outline,
              message: 'No active profile',
              subtitle: 'Choose a reading profile to see its downloads.',
            )
          : TabBarView(
              controller: _tabs,
              children: [
                _ChaptersTab(
                  queueExpanded: _queueExpanded,
                  onToggleQueue: () =>
                      setState(() => _queueExpanded = !_queueExpanded),
                  onOpenStorageSettings: () => _tabs.animateTo(1),
                ),
                const _StorageTab(),
              ],
            ),
    );
  }
}

class _ChaptersTab extends ConsumerWidget {
  const _ChaptersTab({
    required this.queueExpanded,
    required this.onToggleQueue,
    required this.onOpenStorageSettings,
  });

  final bool queueExpanded;
  final VoidCallback onToggleQueue;
  final VoidCallback onOpenStorageSettings;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final groupsAsync = ref.watch(downloadedSeriesProvider);
    final queued =
        ref.watch(activeDownloadQueueProvider).valueOrNull ??
            const <SavedChapter>[];

    // Slivers, not a ListView of everything: both the queue and the saved
    // library are unbounded (a "download series" can be hundreds of
    // chapters), and only slivers keep those rows lazy.
    return CustomScrollView(
      slivers: [
        const SliverToBoxAdapter(child: OcrRunBanner()),
        SliverPadding(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.xl2,
            AppSpacing.lg,
            AppSpacing.xl2,
            0,
          ),
          sliver: SliverToBoxAdapter(
            child: ActiveDownloadsPanel(
              expanded: queueExpanded,
              onToggleExpanded: onToggleQueue,
              onOpenStorageSettings: onOpenStorageSettings,
            ),
          ),
        ),
        if (queueExpanded && queued.isNotEmpty)
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.md,
              AppSpacing.sm,
              AppSpacing.md,
              0,
            ),
            sliver: SliverList.builder(
              itemCount: queued.length,
              itemBuilder: (context, index) =>
                  QueuedChapterRow(chapter: queued[index]),
            ),
          ),
        const SliverPadding(
          padding: EdgeInsets.fromLTRB(
            AppSpacing.xl2,
            AppSpacing.lg,
            AppSpacing.xl2,
            0,
          ),
          sliver: SliverToBoxAdapter(child: _WhereItLivesCard()),
        ),
        ...groupsAsync.when(
          loading: () => const [
            SliverFillRemaining(
              hasScrollBody: false,
              child: Center(child: CircularProgressIndicator()),
            ),
          ],
          error: (error, _) => [
            SliverFillRemaining(
              hasScrollBody: false,
              child: Center(
                child: Text(
                  'Could not load downloads.',
                  style: AppTypography.body.copyWith(color: AppColors.danger),
                ),
              ),
            ),
          ],
          data: (groups) => _savedSlivers(context, groups),
        ),
      ],
    );
  }

  List<Widget> _savedSlivers(
    BuildContext context,
    List<DownloadedSeriesGroup> groups,
  ) {
    if (groups.isEmpty) {
      return const [
        SliverFillRemaining(
          hasScrollBody: false,
          child: EmptyState(
            icon: Icons.download_outlined,
            message: 'No downloads yet',
            subtitle:
                'Chapters you download for offline reading show up here.',
          ),
        ),
      ];
    }

    // Largest series first — this list doubles as the answer to "what is
    // taking up my space", and the per-series breakdown on the Storage tab
    // uses the same ordering for the same reason.
    final ordered = [...groups]
      ..sort((a, b) => b.totalBytes.compareTo(a.totalBytes));

    return [
      SliverPadding(
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.xl2,
          AppSpacing.xl2,
          AppSpacing.xl2,
          AppSpacing.sm,
        ),
        sliver: SliverToBoxAdapter(
          child: Text(
            'On this phone — biggest first',
            style: AppTypography.labelSm.copyWith(
              color: AppColors.muted,
              letterSpacing: 1.0,
            ),
          ),
        ),
      ),
      SliverPadding(
        padding: EdgeInsets.fromLTRB(
          AppSpacing.xl2,
          0,
          AppSpacing.xl2,
          AppSpacing.xl7 + MediaQuery.paddingOf(context).bottom,
        ),
        sliver: SliverList.builder(
          itemCount: ordered.length,
          itemBuilder: (context, index) => Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.md),
            child: _SeriesDownloadCard(group: ordered[index]),
          ),
        ),
      ),
    ];
  }
}

class _StorageTab extends StatelessWidget {
  const _StorageTab();

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.xl2,
        AppSpacing.xl2,
        AppSpacing.xl2,
        AppSpacing.xl7 + MediaQuery.paddingOf(context).bottom,
      ),
      children: const [DownloadsStorageCard()],
    );
  }
}

/// The plain-sentence answer to "where is it landing on my iPhone".
///
/// Deliberately does **not** point at the blob tree. Page bytes are stored
/// content-addressed under `mm-store/blobs/{hash[0:2]}/{sha256}` — that is
/// what makes cross-profile dedup and refcounted deletion correct — so what
/// a user would actually find by going looking is thousands of extensionless
/// files sharded across 256 folders. Telling them to browse that would be
/// technically true and practically useless, so the honest answer is "they
/// live in the app; here is the button that gives you a readable copy".
class _WhereItLivesCard extends StatelessWidget {
  const _WhereItLivesCard();

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.fg.withAlpha(13),
        borderRadius: BorderRadius.circular(AppRadius.md),
        border: Border.all(color: AppColors.border),
      ),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(
              Icons.info_outline,
              color: AppColors.muted,
              size: 18,
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Text(
                'Downloaded chapters are stored inside ManhwaManiacs and read '
                'offline straight from this tab — there is nothing to find in '
                'the Files app. For a copy you can open elsewhere, use Save to '
                'Files on a series or chapter.',
                style: AppTypography.caption.copyWith(
                  color: AppColors.muted,
                  height: 1.5,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SeriesDownloadCard extends ConsumerStatefulWidget {
  const _SeriesDownloadCard({required this.group});

  final DownloadedSeriesGroup group;

  @override
  ConsumerState<_SeriesDownloadCard> createState() => _SeriesDownloadCardState();
}

class _SeriesDownloadCardState extends ConsumerState<_SeriesDownloadCard> {
  var _expanded = false;

  String get _seriesLabel =>
      (widget.group.seriesTitle?.isNotEmpty ?? false)
          ? widget.group.seriesTitle!
          : widget.group.seriesKey;

  @override
  Widget build(BuildContext context) {
    final group = widget.group;
    final saved = group.chapters
        .where((c) => c.state == DownloadChapterState.complete)
        .length;

    return GlassCard(
      padding: EdgeInsets.zero,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          InkWell(
            onTap: () => setState(() => _expanded = !_expanded),
            child: Padding(
              padding: const EdgeInsets.all(AppSpacing.md),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          _seriesLabel,
                          style: AppTypography.labelLg,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        const SizedBox(height: AppSpacing.xxs),
                        Text(
                          _subtitle(saved, group),
                          style: AppTypography.caption
                              .copyWith(color: AppColors.muted),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    key: Key('pin-series-${group.sourceId}-${group.seriesKey}'),
                    tooltip: group.pinned ? 'Unpin series' : 'Pin series',
                    icon: Icon(
                      group.pinned ? Icons.push_pin : Icons.push_pin_outlined,
                      color: group.pinned ? AppColors.primary : AppColors.muted,
                    ),
                    onPressed: () => _togglePin(group),
                  ),
                  PopupMenuButton<_SeriesAction>(
                    key: Key('series-menu-${group.sourceId}-${group.seriesKey}'),
                    tooltip: 'Series options',
                    color: AppColors.surfaceElevated,
                    icon: const Icon(Icons.more_vert, color: AppColors.muted),
                    onSelected: _onSeriesAction,
                    itemBuilder: (context) => const [
                      PopupMenuItem(
                        value: _SeriesAction.export,
                        child: Text('Save to Files…'),
                      ),
                      PopupMenuItem(
                        value: _SeriesAction.deleteAll,
                        child: Text('Remove all downloads'),
                      ),
                    ],
                  ),
                  Icon(
                    _expanded ? Icons.expand_less : Icons.expand_more,
                    color: AppColors.muted,
                  ),
                ],
              ),
            ),
          ),
          if (_expanded)
            for (final chapter in group.chapters)
              _ChapterRow(
                chapter: chapter,
                seriesLabel: _seriesLabel,
                onRemoved: () => ref.invalidate(downloadedSeriesProvider),
              ),
          if (_expanded) const SizedBox(height: AppSpacing.xs),
        ],
      ),
    );
  }

  String _subtitle(int saved, DownloadedSeriesGroup group) {
    final total = group.chapters.length;
    final size = formatDownloadBytes(group.totalBytes);
    if (saved == total) {
      return '$total chapter${total == 1 ? '' : 's'} · $size';
    }
    return '$saved of $total chapters saved · $size';
  }

  Future<void> _onSeriesAction(_SeriesAction action) async {
    switch (action) {
      case _SeriesAction.export:
        await showDownloadExportSheet(
          context,
          ref,
          seriesLabel: _seriesLabel,
          chapters: widget.group.chapters,
        );
      case _SeriesAction.deleteAll:
        await _confirmDeleteAll();
    }
  }

  Future<void> _confirmDeleteAll() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        backgroundColor: AppColors.surfaceElevated,
        title: Text('Remove downloads?', style: AppTypography.h4),
        content: Text(
          'Deletes every downloaded chapter of $_seriesLabel from this phone. '
          'Your reading progress is kept, and you can download them again any '
          'time.',
          style: AppTypography.bodySm.copyWith(color: AppColors.muted),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('Keep'),
          ),
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: Text(
              'Remove',
              style: AppTypography.label.copyWith(color: AppColors.danger),
            ),
          ),
        ],
      ),
    );
    if (confirmed != true) return;

    final store = ref.read(downloadsStoreProvider);
    if (store == null) return;
    for (final chapter in widget.group.chapters) {
      await store.deleteDownload(chapter.identity);
    }
    ref.invalidate(downloadedSeriesProvider);
  }

  Future<void> _togglePin(DownloadedSeriesGroup group) async {
    await ref.read(downloadsStoreProvider)?.setSeriesPinned(
          series: (sourceId: group.sourceId, seriesKey: group.seriesKey),
          pinned: !group.pinned,
        );
    ref.invalidate(downloadedSeriesProvider);
  }
}

enum _SeriesAction { export, deleteAll }

class _ChapterRow extends ConsumerWidget {
  const _ChapterRow({
    required this.chapter,
    required this.seriesLabel,
    required this.onRemoved,
  });

  final SavedChapter chapter;
  final String seriesLabel;
  final VoidCallback onRemoved;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final label = chapterLabel(number: chapter.chapterNumber, title: chapter.title);
    final complete = chapter.state == DownloadChapterState.complete;

    return ListTile(
      dense: true,
      contentPadding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
      title: Text(label.primary, style: AppTypography.bodySm),
      subtitle: Text(
        '${_stateLabel(chapter.state, chapter.error)} · '
        '${formatDownloadBytes(chapter.bytes)}',
        style: AppTypography.caption.copyWith(color: AppColors.muted),
      ),
      onTap: complete
          ? () => context.push(
                RoutePaths.reader(chapter.sourceId, chapter.seriesKey, chapter.chapterKey),
              )
          : null,
      // `mainAxisSize.min` because a ListTile's trailing slot is unbounded:
      // the OCR action hides itself on a device without an engine, and the
      // row must close up rather than leave a gap where it would have been.
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          OcrChapterAction(chapter: chapter),
          if (complete)
            IconButton(
              key: Key(
                'export-${chapter.sourceId}-${chapter.seriesKey}-${chapter.chapterKey}',
              ),
              tooltip: 'Save to Files',
              icon: const Icon(Icons.save_alt, size: 20),
              onPressed: () => showDownloadExportSheet(
                context,
                ref,
                seriesLabel: seriesLabel,
                chapters: [chapter],
              ),
            ),
          IconButton(
            key: Key('remove-${chapter.sourceId}-${chapter.seriesKey}-${chapter.chapterKey}'),
            tooltip: 'Remove download',
            icon: const Icon(Icons.delete_outline, size: 20),
            onPressed: () => _remove(ref),
          ),
        ],
      ),
    );
  }

  String _stateLabel(DownloadChapterState state, String? error) => switch (state) {
        DownloadChapterState.queued => 'Queued',
        DownloadChapterState.downloading => 'Downloading…',
        DownloadChapterState.complete => 'Downloaded',
        DownloadChapterState.failed => error == null ? 'Failed' : 'Failed — $error',
      };

  Future<void> _remove(WidgetRef ref) async {
    await ref.read(downloadsStoreProvider)?.deleteDownload(
          (
            sourceId: chapter.sourceId,
            seriesKey: chapter.seriesKey,
            chapterKey: chapter.chapterKey,
          ),
        );
    onRemoved();
  }
}
