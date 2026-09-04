import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/platform/system_ui.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/providers/progress_outbox_provider.dart';
import 'package:manhwamaniacs/features/downloads/widgets/open_chapter_scope.dart';
import 'package:manhwamaniacs/features/novels/models/novel_chapter.dart';
import 'package:manhwamaniacs/features/novels/models/novel_palette.dart';
import 'package:manhwamaniacs/features/novels/models/novel_typography.dart';
import 'package:manhwamaniacs/features/novels/providers/novel_chapter_provider.dart';
import 'package:manhwamaniacs/features/novels/providers/novel_preferences_provider.dart';
import 'package:manhwamaniacs/features/novels/utils/novel_book.dart';
import 'package:manhwamaniacs/features/novels/utils/novel_progress.dart';
import 'package:manhwamaniacs/features/novels/widgets/novel_chapter_view.dart';
import 'package:manhwamaniacs/features/novels/widgets/novel_reader_chrome.dart';
import 'package:manhwamaniacs/features/novels/widgets/novel_type_panel.dart';
import 'package:manhwamaniacs/features/reader/models/reading_progress.dart';
import 'package:manhwamaniacs/features/reader/utils/reader_wakelock.dart';
import 'package:manhwamaniacs/features/reader/widgets/reader_error_state.dart';
import 'package:manhwamaniacs/features/settings/providers/settings_provider.dart';

/// How often a scroll is turned into a progress position. The manga reader
/// uses the same 500 ms, and for the same reason: often enough that a kill
/// loses nothing worth noticing, rare enough that it is not per-frame work.
const _progressSaveMs = 500;

/// The pause at the end of a chapter before the next one opens.
///
/// This is the manga reader's `_autoNextChapterMs`, deliberately the same
/// number: it is the beat that makes the transition feel like turning a page
/// rather than the app navigating, and two different beats for the two readers
/// would be two different feelings in one app.
const _autoNextChapterMs = 900;

/// Frames a deferred restore is allowed to home in for before it settles
/// wherever it has got to — the same budget and the same reasoning as the
/// manga reader's `_maxRestoreFrames`.
const _maxRestoreFrames = 30;

/// Fraction of the viewport height that counts as the reading line: the
/// paragraph a reader is actually on is the one just below the top edge, not
/// the one clipped by it.
const _readingLineFraction = 0.25;

/// The novel reader.
///
/// Identity is the same opaque `(sourceId, seriesKey, chapterKey)` triple as
/// the manga reader's, and [initialBucket] is the progress BUCKET (see
/// `utils/novel_progress.dart`) carried in the same `?page=` query parameter —
/// so a "Continue" link needs no novel-specific branch to build.
class NovelReaderScreen extends ConsumerWidget {
  const NovelReaderScreen({
    super.key,
    required this.sourceId,
    required this.seriesKey,
    required this.chapterKey,
    this.initialBucket = 1,
  });

  final String sourceId;
  final String seriesKey;
  final String chapterKey;
  final int initialBucket;

  NovelChapterKey get _key =>
      (sourceId: sourceId, seriesKey: seriesKey, chapterKey: chapterKey);

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final chapterAsync = ref.watch(resolvedNovelChapterProvider(_key));
    // Watched, never awaited (spec R3): a downloaded chapter opens off the
    // phone, and what comes next is filled in whenever the network can say.
    final neighbours =
        ref.watch(novelChapterNeighboursProvider(_key)).valueOrNull;

    void retry() {
      // The payload is its own cache entry; invalidating only the resolved
      // provider would re-read its stored error and do nothing visible.
      ref.invalidate(novelChapterPayloadProvider(_key));
      ref.invalidate(resolvedNovelChapterProvider(_key));
    }

    return chapterAsync.when(
      loading: () => const _NovelReaderSkeleton(),
      error: (error, _) {
        final appError = error is AppError
            ? error
            : UnknownError(message: error.toString(), cause: error);
        return ReaderErrorState(
          error: appError,
          onRetry: retry,
          onBack: () => context.pop(),
        );
      },
      data: (chapter) {
        if (chapter.paragraphs.isEmpty) {
          return ReaderErrorState(
            error: const UnknownError(message: 'This chapter has no text.'),
            onRetry: retry,
            onBack: () => context.pop(),
          );
        }
        return OpenChapterScope(
          chapterId: (
            sourceId: sourceId,
            seriesKey: seriesKey,
            chapterKey: chapterKey,
          ),
          child: _NovelReaderBody(
            key: ValueKey('$sourceId:$seriesKey:$chapterKey'),
            chapter: chapter,
            neighbours: neighbours,
            initialBucket: initialBucket,
          ),
        );
      },
    );
  }
}

class _NovelReaderBody extends ConsumerStatefulWidget {
  const _NovelReaderBody({
    super.key,
    required this.chapter,
    required this.neighbours,
    required this.initialBucket,
  });

  final NovelChapter chapter;

  /// Adjacent keys, when the network has supplied them. Kept beside the
  /// chapter rather than folded into it so a later arrival never replaces the
  /// paragraph list this state is measuring against — the reading position
  /// would jump.
  final NovelChapterNeighbours? neighbours;
  final int initialBucket;

  @override
  ConsumerState<_NovelReaderBody> createState() => _NovelReaderBodyState();
}

class _NovelReaderBodyState extends ConsumerState<_NovelReaderBody> {
  final _scrollController = ScrollController();
  late List<GlobalKey> _paragraphKeys;

  bool _chromeVisible = false;

  /// The furthest bucket already handed to the outbox for this chapter.
  /// Scrolling back up must never tell the server the reader is earlier than
  /// they got to — see [nextProgressPush].
  int _furthestSent = 0;

  /// The bucket currently under the reading line, for the read-out.
  int _bucket = 1;

  Timer? _progressTimer;
  Timer? _autoNextTimer;
  bool _autoNextTriggered = false;

  /// The chapter to continue into, from whichever source knows it: the
  /// online payload carries its own, a disk copy learns it out of band.
  String? get _nextKey =>
      widget.chapter.nextChapterKey ?? widget.neighbours?.nextChapterKey;

  String? get _previousKey =>
      widget.chapter.previousChapterKey ?? widget.neighbours?.previousChapterKey;

  int? _pendingRestoreParagraph;
  int _restoreFrames = 0;
  double _lastRestoreMaxExtent = -1;

  @override
  void initState() {
    super.initState();
    _paragraphKeys = List.generate(
      widget.chapter.paragraphs.length,
      (_) => GlobalKey(),
    );
    _scrollController.addListener(_onScroll);
    applyReadingSystemUiMode();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _applyWakelock();
      _beginRestore();
    });
  }

  @override
  void dispose() {
    _progressTimer?.cancel();
    _autoNextTimer?.cancel();
    _scrollController.dispose();
    // Symmetric with initState: leaving a chapter restores exactly what the
    // app launched with rather than permanently changing its shape.
    applyRestingSystemUiMode();
    ref.read(readerWakelockProvider).disable();
    super.dispose();
  }

  void _applyWakelock() {
    final keepAwake = ref.read(readerDefaultsProvider).keepScreenAwake;
    final wakelock = ref.read(readerWakelockProvider);
    keepAwake ? wakelock.enable() : wakelock.disable();
  }

  // ── Restore ──────────────────────────────────────────────────────────────

  /// Resume where the reader left off, never past it.
  ///
  /// The target is a paragraph, but a lazily-built list only knows the offsets
  /// of the paragraphs it has actually laid out — so this homes in the way the
  /// manga reader's restore does: jump as far as the list currently admits,
  /// let that force more paragraphs to lay out, and re-check next frame, under
  /// a hard frame budget so a list whose extent keeps creeping cannot drag the
  /// reader backwards while they are trying to read.
  void _beginRestore() {
    final paragraphs = widget.chapter.paragraphs.length;
    final target = paragraphForBucket(widget.initialBucket, paragraphs);
    if (target <= 0) {
      _bucket = bucketForParagraph(0, paragraphs);
      // Opening at the top is still progress worth remembering as "seen", but
      // never as further than the reader actually got.
      _furthestSent = 0;
      return;
    }
    _pendingRestoreParagraph = target;
    _furthestSent = widget.initialBucket;
    _bucket = widget.initialBucket;
    _restoreFrames = 0;
    _lastRestoreMaxExtent = -1;
    _attemptRestore();
  }

  void _attemptRestore() {
    final target = _pendingRestoreParagraph;
    if (target == null) return;
    if (!mounted || !_scrollController.hasClients) {
      _pendingRestoreParagraph = null;
      return;
    }

    final position = _scrollController.position;
    final box = _boxFor(target);
    if (box != null) {
      // The target has been laid out: land on it exactly.
      final delta = box.localToGlobal(Offset.zero).dy - _viewportTop();
      _scrollController.jumpTo(
        (position.pixels + delta).clamp(0.0, position.maxScrollExtent),
      );
      _pendingRestoreParagraph = null;
      return;
    }

    final maxExtent = position.maxScrollExtent;
    final stoppedGrowing = maxExtent <= _lastRestoreMaxExtent;
    final outOfFrames = ++_restoreFrames >= _maxRestoreFrames;
    if (stoppedGrowing || outOfFrames) {
      _pendingRestoreParagraph = null;
      return;
    }
    _lastRestoreMaxExtent = maxExtent;
    // Jump to where the target is *estimated* to be, which forces the list to
    // build that far and makes the exact answer available next frame.
    final fraction = target / widget.chapter.paragraphs.length;
    _scrollController.jumpTo((maxExtent * fraction).clamp(0.0, maxExtent));
    WidgetsBinding.instance.addPostFrameCallback((_) => _attemptRestore());
  }

  RenderBox? _boxFor(int paragraphIndex) {
    if (paragraphIndex < 0 || paragraphIndex >= _paragraphKeys.length) {
      return null;
    }
    final context = _paragraphKeys[paragraphIndex].currentContext;
    final box = context?.findRenderObject();
    return box is RenderBox && box.hasSize ? box : null;
  }

  double _viewportTop() {
    final box = context.findRenderObject();
    if (box is! RenderBox || !box.hasSize) return 0;
    return box.localToGlobal(Offset.zero).dy;
  }

  // ── Progress ─────────────────────────────────────────────────────────────

  void _onScroll() {
    if (_pendingRestoreParagraph != null) return;
    _progressTimer ??= Timer(
      const Duration(milliseconds: _progressSaveMs),
      () {
        _progressTimer = null;
        _recordPosition();
      },
    );
    _maybeScheduleAutoNext();
  }

  /// Which paragraph is under the reading line, and what that means for
  /// progress.
  ///
  /// Only the paragraphs the list has actually built have offsets to measure,
  /// which is exactly the handful on screen — so the sparse set is collected
  /// here and [activeParagraphIndex] (a pure function, tested without a widget
  /// tree) picks from it.
  void _recordPosition() {
    if (!mounted || !_scrollController.hasClients) return;

    final readingLine = _viewportTop() +
        MediaQuery.sizeOf(context).height * _readingLineFraction;
    final attached = <int>[];
    final offsets = <double>[];
    for (var i = 0; i < _paragraphKeys.length; i++) {
      final box = _boxFor(i);
      if (box == null) continue;
      attached.add(i);
      offsets.add(box.localToGlobal(Offset.zero).dy);
    }
    if (attached.isEmpty) return;

    final paragraph = attached[activeParagraphIndex(offsets, readingLine)];
    final position = progressForParagraph(
      paragraph,
      widget.chapter.paragraphs.length,
    );
    if (position.bucket != _bucket) {
      setState(() => _bucket = position.bucket);
    }

    final push = nextProgressPush(position, _furthestSent);
    if (push == null) return;
    _furthestSent = push.bucket;
    unawaited(_saveProgress(push));
  }

  /// Local-first, exactly like the manga reader: every save goes to the
  /// on-device outbox and is flushed best-effort, so the reader never blocks
  /// on — or loses a save to — a flaky connection. The bucket rides in
  /// `last_page` and the bucket count in `page_count`, which is what lets the
  /// server's furthest-wins merge, the library's "continue reading" and the
  /// statistics service all work with no change at all.
  Future<void> _saveProgress(NovelProgressPosition position) async {
    final chapter = widget.chapter;
    await ref.read(progressOutboxControllerProvider).save(
          ProgressPush(
            sourceId: chapter.sourceId,
            seriesKey: chapter.seriesKey,
            chapterKey: chapter.chapterKey,
            chapterNumber: chapter.chapterNumber,
            lastPage: position.bucket,
            pageCount: position.buckets,
            isCompleted: position.completed,
          ),
        );
    if (position.completed) {
      // Read-then-expire: starts the 48h phone-copy timer. A no-op when this
      // chapter was never downloaded.
      await ref.read(downloadsStoreProvider)?.markRead(
            (
              sourceId: chapter.sourceId,
              seriesKey: chapter.seriesKey,
              chapterKey: chapter.chapterKey,
            ),
          );
    }
  }

  // ── Seamless continuation ────────────────────────────────────────────────

  /// The manga reader's mechanism, unchanged: at the end of the chapter, if
  /// the user's auto-next preference is on and there is a next chapter, wait
  /// [_autoNextChapterMs] and go. Once per chapter — [_autoNextTriggered]
  /// makes a bounce at the bottom, or a second scroll event in the same
  /// window, incapable of firing it twice.
  void _maybeScheduleAutoNext() {
    final next = _nextKey;
    if (!ref.read(readerDefaultsProvider).autoNextChapter ||
        next == null ||
        _autoNextTriggered ||
        !_atEnd()) {
      _autoNextTimer?.cancel();
      _autoNextTimer = null;
      return;
    }
    if (_autoNextTimer != null) return;
    _autoNextTimer = Timer(
      const Duration(milliseconds: _autoNextChapterMs),
      () {
        if (!mounted || _autoNextTriggered) return;
        _autoNextTriggered = true;
        _openChapter(next);
      },
    );
  }

  bool _atEnd() {
    if (!_scrollController.hasClients) return false;
    final position = _scrollController.position;
    return position.pixels >= position.maxScrollExtent - 8;
  }

  void _openChapter(String chapterKey) {
    // `go`, not `push`: continuing a book replaces the chapter rather than
    // stacking one on top of the last, so Back always leaves the reader
    // instead of walking backwards through everything just read.
    context.go(
      RoutePaths.novelReader(
        widget.chapter.sourceId,
        widget.chapter.seriesKey,
        chapterKey,
      ),
    );
  }

  // ── Build ────────────────────────────────────────────────────────────────

  NovelSurfaceColors _surface(BuildContext context) {
    final stored = ref.watch(novelPaletteControllerProvider);
    final choice = NovelPalettes.resolveChoice(
      stored,
      appIsDark: Theme.of(context).brightness == Brightness.dark,
    );
    final palette = NovelPalettes.byId(choice);
    if (palette != null) return NovelSurfaceColors.fromPalette(palette);
    // "Follow app theme": inherit the app's own tokens rather than painting a
    // surface, so one rendering path covers both cases.
    final colors = context.colors;
    return NovelSurfaceColors(
      bg: colors.bg,
      ink: colors.fg,
      muted: colors.muted,
      isDark: Theme.of(context).brightness == Brightness.dark,
    );
  }

  @override
  Widget build(BuildContext context) {
    final chapter = widget.chapter;
    final surface = _surface(context);
    final prefsKey = novelSeriesPrefsKey(chapter.sourceId, chapter.seriesKey);
    final prefs = ref.watch(novelPreferencesControllerProvider(prefsKey));
    final width = MediaQuery.sizeOf(context).width;
    final column = novelColumnWidth(
      measure: prefs.measure,
      fontSize: prefs.fontSize,
      available: width - 40,
    );

    return Scaffold(
      backgroundColor: surface.bg,
      body: Stack(
        children: [
          GestureDetector(
            behavior: HitTestBehavior.translucent,
            onTap: () => setState(() => _chromeVisible = !_chromeVisible),
            child: Scrollbar(
              controller: _scrollController,
              child: CustomScrollView(
                controller: _scrollController,
                slivers: [
                  SliverPadding(
                    padding: EdgeInsets.symmetric(
                      horizontal: (width - column) / 2,
                    ),
                    sliver: SliverList.list(
                      children: [
                        SizedBox(height: MediaQuery.paddingOf(context).top + 72),
                        _ChapterHeading(
                          chapter: chapter,
                          surface: surface,
                          preferences: prefs,
                        ),
                      ],
                    ),
                  ),
                  SliverPadding(
                    padding: EdgeInsets.symmetric(
                      horizontal: (width - column) / 2,
                    ),
                    sliver: NovelChapterView(
                      paragraphs: chapter.paragraphs,
                      palette: surface,
                      preferences: prefs,
                      paragraphKeys: _paragraphKeys,
                    ),
                  ),
                  SliverToBoxAdapter(
                    child: _ChapterFoot(
                      chapter: chapter,
                      surface: surface,
                      onNext: _nextKey == null
                          ? null
                          : () => _openChapter(_nextKey!),
                    ),
                  ),
                ],
              ),
            ),
          ),
          NovelReaderChrome(
            visible: _chromeVisible,
            surface: surface,
            title: chapter.title,
            percent: chapterPercent(_bucket, chapter.buckets),
            isOffline: chapter.isOffline,
            onBack: () => context.pop(),
            onPrevious: _previousKey == null
                ? null
                : () => _openChapter(_previousKey!),
            onNext: _nextKey == null ? null : () => _openChapter(_nextKey!),
            onType: () => NovelTypePanel.show(
              context,
              seriesPrefsKey: prefsKey,
              surface: surface,
            ),
          ),
        ],
      ),
    );
  }
}

/// The chapter's own front matter: number, title, length. Set as a book sets a
/// chapter opening — centred, with real air under it, so the first paragraph
/// starts on a clean page rather than immediately under a heading.
class _ChapterHeading extends StatelessWidget {
  const _ChapterHeading({
    required this.chapter,
    required this.surface,
    required this.preferences,
  });

  final NovelChapter chapter;
  final NovelSurfaceColors surface;
  final NovelPreferences preferences;

  @override
  Widget build(BuildContext context) {
    final stack = novelFontStack(preferences.fontFamily);
    final number = chapter.chapterNumber;
    return Padding(
      padding: const EdgeInsets.only(bottom: 36),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (number != null)
            Text(
              'Chapter ${formatChapterNumber(number)}',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 12,
                letterSpacing: 2.4,
                fontWeight: FontWeight.w600,
                color: surface.muted,
              ),
            ),
          const SizedBox(height: 10),
          Text(
            chapter.title,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontFamily: stack.first,
              fontFamilyFallback: stack.sublist(1),
              fontSize: preferences.fontSize * 1.55,
              height: 1.25,
              fontWeight: FontWeight.w600,
              color: surface.ink,
            ),
          ),
          const SizedBox(height: 14),
          Center(
            child: Container(width: 48, height: 1, color: surface.rule),
          ),
          const SizedBox(height: 14),
          Text(
            formatChapterLength(chapter.wordCount) ?? '',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 12, color: surface.muted),
          ),
        ],
      ),
    );
  }
}

class _ChapterFoot extends StatelessWidget {
  const _ChapterFoot({
    required this.chapter,
    required this.surface,
    required this.onNext,
  });

  final NovelChapter chapter;
  final NovelSurfaceColors surface;
  final VoidCallback? onNext;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(
        24,
        48,
        24,
        MediaQuery.paddingOf(context).bottom + 72,
      ),
      child: Column(
        children: [
          Container(width: 48, height: 1, color: surface.rule),
          const SizedBox(height: 24),
          if (onNext != null)
            OutlinedButton(
              onPressed: onNext,
              style: OutlinedButton.styleFrom(
                foregroundColor: surface.ink,
                side: BorderSide(color: surface.rule),
                padding: const EdgeInsets.symmetric(
                  horizontal: 24,
                  vertical: 14,
                ),
              ),
              child: const Text('Next chapter'),
            )
          else
            Text(
              chapter.isOffline
                  ? 'End of the downloaded copy'
                  : 'End of the book, for now',
              style: TextStyle(fontSize: 13, color: surface.muted),
            ),
        ],
      ),
    );
  }
}

class _NovelReaderSkeleton extends StatelessWidget {
  const _NovelReaderSkeleton();

  @override
  Widget build(BuildContext context) => Scaffold(
        backgroundColor: NovelPalettes.dusk.bg,
        body: Center(
          child: CircularProgressIndicator(color: NovelPalettes.dusk.muted),
        ),
      );

}
