import 'dart:async';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart' show ScrollCacheExtent;
import 'package:flutter/scheduler.dart' show SchedulerBinding, SchedulerPhase;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/core/network/api_image.dart';
import 'package:manhwamaniacs/core/platform/native_bridge.dart';
import 'package:manhwamaniacs/core/platform/system_ui.dart';
import 'package:manhwamaniacs/core/utils/haptics.dart';
import 'package:manhwamaniacs/features/profiles/providers/profiles_providers.dart';
import 'package:manhwamaniacs/features/reader/models/reader_chapter.dart';
import 'package:manhwamaniacs/features/reader/models/reader_feed.dart';
import 'package:manhwamaniacs/features/reader/providers/reader_filter_provider.dart';
import 'package:manhwamaniacs/features/reader/providers/reader_ui_provider.dart';
import 'package:manhwamaniacs/features/reader/utils/page_extents.dart';
import 'package:manhwamaniacs/features/reader/utils/page_layout.dart';
import 'package:manhwamaniacs/features/reader/utils/reader_display_mode.dart';
import 'package:manhwamaniacs/features/reader/utils/reader_image_cache.dart';
import 'package:manhwamaniacs/features/reader/utils/reader_scroll_controller.dart';
import 'package:manhwamaniacs/features/reader/utils/reader_wakelock.dart';
import 'package:manhwamaniacs/features/reader/utils/scroll_storage.dart';
import 'package:manhwamaniacs/features/reader/widgets/chapter_seam.dart';
import 'package:manhwamaniacs/features/reader/widgets/reader_controls.dart';
import 'package:manhwamaniacs/features/reader/widgets/reader_edge_back_gesture.dart';
import 'package:manhwamaniacs/features/reader/widgets/reader_page_image.dart';
import 'package:manhwamaniacs/features/reader/widgets/reader_shortcuts.dart';
import 'package:manhwamaniacs/features/settings/models/reader_defaults.dart';
import 'package:manhwamaniacs/features/settings/providers/settings_provider.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _scrollSaveMs = 250;
const _progressSaveMs = 500;
const _autoNextChapterMs = 900;

/// Minimum milliseconds after a scroll event before a tap is treated as intentional.
const _postScrollCooldownMs = 300;

/// Max gap between two taps to register a double-tap (zoom toggle).
const _doubleTapMs = 280;

/// Frames a deferred scroll-restore is allowed to home in for before it settles
/// wherever it has got to. See [_ReaderContentState._attemptRestoreJump].
const _maxRestoreFrames = 30;

/// Longest frame delta auto-scroll will honour. Beyond this (a stall, GC pause
/// or the app returning from the background) we fall back to a single 60 fps
/// step so scrolling never lurches forward by a huge jump.
const _autoScrollMaxFrameSeconds = 0.1;

/// Pixels to advance auto-scroll for one frame lasting [dtSeconds], given a
/// target [speedPxPerSecond]. Frame-rate independent by design: driving this
/// off the real frame delta (rather than assuming 60 fps) keeps "Slow" the same
/// physical speed on 60, 90 and 120 Hz panels — the reader supports all three.
double autoScrollFrameDelta(double speedPxPerSecond, double dtSeconds) {
  if (dtSeconds <= 0 || dtSeconds > _autoScrollMaxFrameSeconds) {
    dtSeconds = 1 / 60;
  }
  return speedPxPerSecond * dtSeconds;
}

/// Shared reader body used by both the local library reader and the online
/// source reader.
///
/// It owns no data fetching and no persistence — callers pass the resolved
/// [ReaderFeed] plus optional callbacks for progress/bookmark saves and
/// chapter navigation. Every reader behaviour (fullscreen, scroll restore,
/// zoom, virtualized page list, cached images, edge prompts, auto-next) lives
/// here exactly once so the two entry points cannot drift.
///
/// It renders a FEED, not a chapter (spec R1). A feed of one is the ordinary
/// read and behaves exactly as it always did; a feed of several is one
/// continuous scroll across a chapter boundary, with the seam marked and
/// never blocking. Growing the feed is the caller's job — this widget only
/// says *when* ([onReachedFeedEnd] / [onReachedFeedStart]) — because only the
/// caller knows how to fetch a chapter and which one comes next.
class ReaderContent extends ConsumerStatefulWidget {
  const ReaderContent({
    super.key,
    required this.feed,
    required this.scrollStorageKey,
    required this.onBack,
    required this.onOpenSeries,
    this.initialPage = 1,
    this.showBookmark = true,
    this.onSaveProgress,
    this.onAddBookmark,
    this.onPreviousChapter,
    this.onNextChapter,
    this.onReachedFeedEnd,
    this.onReachedFeedStart,
    this.pageExtents,
  });

  /// The chapters being read, as one page list. [ReaderFeed.single] is the
  /// ordinary case.
  final ReaderFeed feed;

  /// Opaque key used to persist/restore scroll position for the chapter this
  /// reader was OPENED at — the feed's anchor. Positions inside chapters the
  /// feed later grew into are carried by reading progress instead, which is
  /// per-chapter and already saved.
  final String scrollStorageKey;
  final int initialPage;
  final bool showBookmark;
  final VoidCallback onBack;

  /// Open the series page for this chapter, so the chapter list is reachable
  /// without retracing however the reader was entered. Required rather than
  /// optional: both entry points always know their series, and a null here
  /// would silently remove the only affordance for it.
  final VoidCallback onOpenSeries;

  /// Persist reading progress. Only the local library reader supplies this.
  ///
  /// Takes the chapter as well as the page because a continuous feed spans
  /// several: reading into chapter 12 has to record chapter 12, page N — the
  /// page number is chapter-local, never an index into the feed.
  final Future<void> Function(ReaderChapter chapter, int page)? onSaveProgress;

  /// Create a bookmark at the visible page of the chapter it belongs to. Only
  /// the local library reader. Return ``true`` when it was saved.
  final Future<bool> Function(ReaderChapter chapter, int page)? onAddBookmark;

  /// Navigate to the previous/next chapter as a fresh route. ``null`` disables
  /// that direction. In a continuous feed these are the edge prompts for a
  /// boundary the feed could not absorb (nothing beyond it, or the fetch
  /// failed) — crossing a loaded boundary never navigates.
  final VoidCallback? onPreviousChapter;
  final VoidCallback? onNextChapter;

  /// Called as the reader comes within [kSeamPrefetchPages] of either end of
  /// the feed, so the caller can fetch the adjacent chapter and hand back a
  /// longer feed **before** the seam is reached. Null in single-chapter mode,
  /// which is what keeps that mode exactly as it was.
  final Future<void> Function()? onReachedFeedEnd;
  final Future<void> Function()? onReachedFeedStart;

  /// Page geometry for this feed. The reader owns one per session when this
  /// is omitted; supplying it lets a test resolve a page's real size without a
  /// decoding image, which is otherwise unreachable from outside.
  final ReaderPageExtents? pageExtents;

  @override
  ConsumerState<ReaderContent> createState() => _ReaderContentState();
}

class _ReaderContentState extends ConsumerState<ReaderContent> {
  late final ReaderScrollController _scrollController;
  late final ReaderPageExtents _pageExtents;
  late final bool _ownsPageExtents;
  ReaderPageMetrics? _cachedMetrics;
  var _extentCommitScheduled = false;
  SharedPreferences? _prefs;
  ReaderWakelock? _wakelock;
  ReaderDisplayMode? _displayMode;
  NativeBridge? _nativeBridge;
  ReaderRefreshRate? _appliedRefreshRate;
  StreamSubscription<VolumeKeyDirection>? _volumeKeySubscription;
  Timer? _scrollSaveTimer;
  Timer? _progressSaveTimer;
  Timer? _autoNextTimer;
  Timer? _hideControlsTimer;

  // Scroll-driven state — ValueNotifiers avoid any rebuild on scroll
  final _positionNotifier = ValueNotifier<ReaderFeedPosition>(
    (
      flatIndex: 0,
      chapterIndex: 0,
      page: 1,
      pageCount: 1,
      chapterTitle: '',
    ),
  );
  final _atStartNotifier = ValueNotifier<bool>(false);
  final _atEndNotifier = ValueNotifier<bool>(false);

  // Only bookmark pending still needs setState (affects Scaffold snackbar path)
  var _bookmarkPending = false;

  // Auto-scroll state
  bool _autoScrollActive = false;
  Duration? _lastAutoScrollFrame;

  /// The last progress actually handed to [ReaderContent.onSaveProgress], and
  /// the one waiting on the debounce — both carry the chapter, because in a
  /// feed "page 3" means nothing without saying page 3 of what.
  (String chapterId, int page)? _lastSaved;
  (ReaderChapter chapter, int page)? _pending;
  var _initialScrollApplied = false;

  /// The chapter this reader was opened at. Scroll offsets are persisted
  /// relative to it and only while it is the one on screen; everything else
  /// resumes through per-chapter reading progress.
  late final String _anchorChapterId = widget.feed.chapters.isEmpty
      ? ''
      : widget.feed.chapters.first.id;

  /// One adjacent-chapter request in flight per direction. A failed request
  /// simply lets the next scroll event try again, which cannot spin: every
  /// attempt is a network round trip.
  var _loadingNext = false;
  var _loadingPrevious = false;

  // Deferred scroll-restore state. On a long webtoon the ListView.builder has
  // only laid out the viewport + cache extent on the first frame, so the true
  // maxScrollExtent is far smaller than a deep saved offset. We jump toward the
  // target across successive frames (each jump forces more pages to lay out and
  // grows maxScrollExtent) until we can land on it, and suppress scroll saves in
  // the meantime so a clamped-short interim offset never overwrites the saved one.
  double? _pendingRestoreOffset;
  double _lastRestoreMaxExtent = -1;
  var _restoreFrames = 0;
  var _autoNextTriggered = false;
  var _wakelockEnabled = false;
  var _lockInitialized = false;
  var _prefetchedThrough = 0;
  var _volumeKeyNavEnabled = false;

  // Tap-detection state
  bool _isScrolling = false;
  DateTime _lastScrollEnd = DateTime.fromMillisecondsSinceEpoch(0);
  Offset? _tapDownPosition;
  int _consecutiveCenterTaps = 0;
  DateTime _lastCenterTapTime = DateTime.fromMillisecondsSinceEpoch(0);
  DateTime _lastTapTime = DateTime.fromMillisecondsSinceEpoch(0);

  double? _containerWidth;
  double? _containerHeight;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _prefs ??= ref.read(sharedPrefsProvider);
    _wakelock ??= ref.read(readerWakelockProvider);
    _displayMode ??= ref.read(readerDisplayModeProvider);
    _nativeBridge ??= ref.read(nativeBridgeProvider);
  }

  @override
  void initState() {
    super.initState();
    _positionNotifier.value = _positionAt(
      widget.feed.flatIndexOf(
            chapterId: _anchorChapterId,
            page: widget.initialPage,
          ) ??
          0,
    );
    _ownsPageExtents = widget.pageExtents == null;
    _pageExtents = widget.pageExtents ?? ReaderPageExtents(widget.feed.pages);
    _pageExtents.addListener(_handleExtentSubmission);
    _scrollController = ReaderScrollController()..addListener(_handleScroll);
    unawaited(tuneReaderImageCache(ref.read(nativeBridgeProvider)));
    unawaited(applyReadingSystemUiMode());
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _restoreInitialScroll();
      final defaults = ref.read(readerDefaultsProvider);
      _syncWakelock(defaults.keepScreenAwake);
      _syncRefreshRate(defaults.refreshRate);
      _syncVolumeKeyNav(defaults.volumeKeyNavigation);
      // Apply lock mode from settings (once per session)
      if (!_lockInitialized && defaults.lockControls) {
        ref.read(readerUiProvider.notifier).setLocked(true);
        _lockInitialized = true;
      }
      // Start the auto-hide timer for the initial controls display
      _scheduleHideControls();
      // readerUiProvider is app-scoped, so autoScrollEnabled survives a
      // chapter transition (context.go rebuilds a fresh state). The build-time
      // listener only fires on a change, never on this initial mount, so
      // without this the toggle would read ON while scrolling had silently
      // stopped. Resume it here so the persisted state and behaviour agree.
      if (ref.read(readerUiProvider).autoScrollEnabled) {
        _startAutoScroll();
      }
    });
  }

  @override
  void didUpdateWidget(covariant ReaderContent oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(oldWidget.feed, widget.feed)) {
      _reconcileFeed(oldWidget.feed, widget.feed);
    }
  }

  /// Fold a grown or trimmed feed into the geometry **without moving what the
  /// reader is looking at**.
  ///
  /// Appending is free: every existing index keeps its meaning and the pages
  /// simply continue past the old end. Prepending and releasing are not —
  /// they shift every index, and with it every pixel above the viewport, so
  /// the scroll offset has to move by exactly the extent that appeared or
  /// disappeared above. That correction is the whole reason [ReaderFeed] is
  /// immutable: the difference between the two feeds is recoverable.
  ///
  /// Anything that is not one of those four shapes rebuilds the extents, which
  /// costs a re-measure but cannot be wrong.
  void _reconcileFeed(ReaderFeed before, ReaderFeed after) {
    _cachedMetrics = null;
    final oldIds = [for (final chapter in before.chapters) chapter.id];
    final newIds = [for (final chapter in after.chapters) chapter.id];
    bool sameIds(List<String> a, List<String> b) =>
        a.length == b.length &&
        List.generate(a.length, (i) => a[i] == b[i]).every((match) => match);

    // Appended — the forward seam. Nothing above the viewport changed.
    if (newIds.length > oldIds.length &&
        sameIds(newIds.sublist(0, oldIds.length), oldIds)) {
      _pageExtents.appendPages(after.pages.sublist(before.length));
      return;
    }

    // Prepended — the backward seam. Everything moved down by the extent of
    // the new pages plus the seam divider now sitting above the old first one.
    if (newIds.length > oldIds.length &&
        sameIds(newIds.sublist(newIds.length - oldIds.length), oldIds)) {
      final added = after.length - before.length;
      _abandonPendingRestore();
      _pageExtents.prependPages(after.pages.sublist(0, added));
      _prefetchedThrough += added;
      final metrics = _cachedMetrics = _buildMetrics();
      _scrollController.applyExtentCorrection(
        metrics.offsetToPage(added + 1) +
            metrics.leadingInsetAt(added) -
            readerListLeadingPadding,
      );
      return;
    }

    // Released from the front — Read-all letting go of what is far behind.
    if (newIds.length < oldIds.length &&
        sameIds(oldIds.sublist(oldIds.length - newIds.length), newIds)) {
      final removed = before.length - after.length;
      final old = _cachedMetrics;
      final delta = old == null
          ? 0.0
          : old.offsetToPage(removed + 1) +
              old.leadingInsetAt(removed) -
              readerListLeadingPadding;
      _abandonPendingRestore();
      _pageExtents.removeLeadingPages(removed);
      _prefetchedThrough = (_prefetchedThrough - removed).clamp(0, after.length);
      _cachedMetrics = _buildMetrics();
      _scrollController.applyExtentCorrection(-delta);
      return;
    }

    // Released from the end. Below the viewport by definition, so nothing to
    // correct — only the prefetch high-water mark to pull back.
    if (newIds.length < oldIds.length &&
        sameIds(oldIds.sublist(0, newIds.length), newIds)) {
      _pageExtents.removeTrailingPages(before.length - after.length);
      _prefetchedThrough = _prefetchedThrough.clamp(0, after.length);
      return;
    }

    // Not a shape this widget produces — a caller replaced the feed wholesale.
    // Start the geometry over rather than guessing what moved.
    if (_ownsPageExtents) {
      _abandonPendingRestore();
      _pageExtents
        ..removeTrailingPages(before.length)
        ..appendPages(after.pages);
      _prefetchedThrough = 0;
    }
  }

  @override
  void dispose() {
    _stopAutoScroll();
    _flushProgress();
    _scrollSaveTimer?.cancel();
    _progressSaveTimer?.cancel();
    _autoNextTimer?.cancel();
    _autoNextTimer = null;
    _hideControlsTimer?.cancel();
    unawaited(_releaseWakelock());
    unawaited(_displayMode?.reset());
    unawaited(_syncVolumeKeyNav(false));
    unawaited(_volumeKeySubscription?.cancel());
    if (_scrollController.hasClients &&
        _prefs != null &&
        _positionNotifier.value.chapterIndex == _anchorIndex) {
      final relative =
          _scrollController.offset - _anchorOrigin + readerListLeadingPadding;
      writeReaderScrollPositionByKey(
        _prefs!,
        _scrollKey,
        relative < 0 ? 0 : relative,
      );
    }
    _scrollController.dispose();
    _pageExtents.removeListener(_handleExtentSubmission);
    if (_ownsPageExtents) _pageExtents.dispose();
    _positionNotifier.dispose();
    _atStartNotifier.dispose();
    _atEndNotifier.dispose();
    // Restore what the app launched with rather than hardcoding edgeToEdge:
    // on iOS that call was the only thing that ever un-hid the status bar, so
    // the app silently changed shape the first time a chapter was closed.
    unawaited(applyRestingSystemUiMode());
    super.dispose();
  }

  SharedPreferences _resolvedPrefs() => _prefs ?? ref.read(sharedPrefsProvider);

  /// Scroll-resume key namespaced by the active profile. This is a household /
  /// multi-profile app, so persisting under the bare chapter key leaked one
  /// persona's reading position into another's session (both readers shared a
  /// single SharedPreferences entry per chapter). Prefixing with the active
  /// profile id keeps each persona's position private.
  String get _scrollKey =>
      '${ref.read(activeProfileProvider)?.id ?? 'none'}:${widget.scrollStorageKey}';

  /// Where the anchor chapter sits in the feed, or -1 once a Read-all window
  /// has released it.
  int get _anchorIndex => widget.feed.indexOfChapter(_anchorChapterId);

  /// Scroll offset of the anchor chapter's first page. Offsets are persisted
  /// relative to this, so a chapter prepended above it — which shifts every
  /// absolute offset in the feed — does not silently invalidate a saved
  /// position.
  double get _anchorOrigin {
    final index = _anchorIndex;
    if (index <= 0) return readerListLeadingPadding;
    return _metrics.offsetToPage(widget.feed.startOfChapter(index) + 1);
  }

  /// The feed position for a flat page index — the one place the reader's
  /// coordinate (an index into the whole feed) is turned into the reader's
  /// meaning (a chapter and a page in it).
  ReaderFeedPosition _positionAt(int flatIndex) {
    final feed = widget.feed;
    if (feed.isEmpty) {
      return (
        flatIndex: 0,
        chapterIndex: 0,
        page: 1,
        pageCount: 1,
        chapterTitle: '',
      );
    }
    final index = flatIndex.clamp(0, feed.length - 1);
    final chapter = feed.chapterAt(index);
    return (
      flatIndex: index,
      chapterIndex: feed.chapterIndexAt(index),
      page: feed.pageWithinChapterAt(index),
      pageCount: chapter.pages.length,
      chapterTitle: chapter.title,
    );
  }

  /// Extra space reserved above the first page of every chapter after the
  /// first — the seam divider, as geometry rather than as a widget the list
  /// happens to contain. Empty for a single-chapter feed, which is what keeps
  /// that case pixel-identical to before.
  Map<int, double> get _seamInsets {
    final feed = widget.feed;
    if (feed.isSingleChapter) return const {};
    return {
      for (var c = 1; c < feed.chapters.length; c++)
        feed.startOfChapter(c): kChapterSeamExtent,
    };
  }

  ReaderDefaults get _defaults => ref.read(readerDefaultsProvider);

  Haptics get _haptics => ref.read(hapticsProvider);

  Future<void> _syncWakelock(bool enabled) async {
    final wakelock = _wakelock;
    if (wakelock == null) return;

    if (enabled && !_wakelockEnabled) {
      await wakelock.enable();
      _wakelockEnabled = true;
      return;
    }

    if (!enabled && _wakelockEnabled) {
      await _releaseWakelock();
    }
  }

  /// Enable/disable hardware volume-key page turning. Subscribes to the
  /// native bridge's event stream only while enabled, and always disables
  /// native interception on dispose so leaving the reader restores normal
  /// volume behaviour everywhere else in the app.
  Future<void> _syncVolumeKeyNav(bool enabled) async {
    if (enabled == _volumeKeyNavEnabled) return;
    _volumeKeyNavEnabled = enabled;

    final bridge = _nativeBridge;
    if (bridge == null) return;

    if (enabled) {
      _volumeKeySubscription ??= bridge.volumeKeyEvents.listen(_handleVolumeKey);
      await bridge.setVolumeKeyNavEnabled(true);
    } else {
      await bridge.setVolumeKeyNavEnabled(false);
      await _volumeKeySubscription?.cancel();
      _volumeKeySubscription = null;
    }
  }

  void _handleVolumeKey(VolumeKeyDirection direction) {
    if (!mounted) return;
    _pageBy(forward: direction == VolumeKeyDirection.down);
  }

  Future<void> _releaseWakelock() async {
    if (!_wakelockEnabled) return;
    await _wakelock?.disable();
    _wakelockEnabled = false;
  }

  void _syncRefreshRate(ReaderRefreshRate rate) {
    if (_appliedRefreshRate == rate) return;
    _appliedRefreshRate = rate;
    unawaited(_displayMode?.apply(rate));
  }

  /// Page geometry for the current layout. Rebuilt on every [build] (viewport,
  /// zoom, direction and fit all feed it) and thrown away whenever a page's real
  /// size lands, so nothing ever reads a stale extent.
  ReaderPageMetrics get _metrics => _cachedMetrics ??= _buildMetrics();

  ReaderPageMetrics _buildMetrics() {
    final defaults = _defaults;
    return ReaderPageMetrics.of(
      _pageExtents,
      direction: defaults.direction,
      fitMode: defaults.fitMode,
      viewportWidth: _containerWidth ?? MediaQuery.sizeOf(context).width,
      viewportHeight: _containerHeight ?? MediaQuery.sizeOf(context).height,
      zoom: ref.read(readerUiProvider).zoomLevel,
      leadingInsets: _seamInsets,
    );
  }

  void _restoreInitialScroll() {
    if (_initialScrollApplied || !_scrollController.hasClients) return;

    final prefs = _resolvedPrefs();
    final savedScroll = readReaderScrollPositionByKey(prefs, _scrollKey);
    final feed = widget.feed;
    final targetFlat = feed.flatIndexOf(
          chapterId: _anchorChapterId,
          page: widget.initialPage,
        ) ??
        0;
    final initialOffset = resolveInitialScrollTop(
      // Stored relative to the anchor chapter; the feed is that one chapter
      // at open time, so this is the identity in the ordinary case.
      savedScroll: savedScroll == null ? null : savedScroll + _anchorOrigin - readerListLeadingPadding,
      initialPage: widget.initialPage.clamp(1, feed.length),
      pageCount: feed.length,
      estimatedOffsetToPage: _metrics.offsetToPage(targetFlat + 1),
    );

    if (initialOffset <= 0) {
      _initialScrollApplied = true;
      _handleScroll();
      return;
    }

    // Defer the jump: the target offset may exceed the still-growing
    // maxScrollExtent on this first frame. _attemptRestoreJump nudges the list
    // forward frame by frame until it can land exactly on [initialOffset].
    _pendingRestoreOffset = initialOffset;
    _lastRestoreMaxExtent = -1;
    _restoreFrames = 0;
    _attemptRestoreJump();
  }

  /// Give up on a restore that is still homing in.
  ///
  /// Marks the restore as applied so scroll saves resume; leaving
  /// [_pendingRestoreOffset] set would silently stop the reader ever persisting
  /// a position again for this chapter.
  void _abandonPendingRestore() {
    if (_pendingRestoreOffset == null) return;
    _pendingRestoreOffset = null;
    _initialScrollApplied = true;
  }

  /// Drive the deferred scroll-restore. Called once per frame while a restore is
  /// pending. Each interim jump extends the ListView.builder's laid-out range,
  /// so [maxScrollExtent] grows until it reaches the saved offset — at which
  /// point we land exactly on it. If the list stops growing before reaching the
  /// target (chapter genuinely shorter than the estimate), we settle at the real
  /// end. Only once landed do we mark [_initialScrollApplied] and let scroll
  /// saves resume, so a clamped-short interim offset can never be persisted.
  void _attemptRestoreJump() {
    final target = _pendingRestoreOffset;
    if (target == null) return;
    if (!mounted || !_scrollController.hasClients) {
      _abandonPendingRestore();
      return;
    }

    final maxExtent = _scrollController.position.maxScrollExtent;
    final reachedTarget = maxExtent >= target;
    final stoppedGrowing = maxExtent <= _lastRestoreMaxExtent;
    // The list reports the chapter's true extent from the first frame now, so a
    // restore lands on its first attempt. The budget is the backstop for a list
    // whose extent keeps creeping — without it a homing loop of jumpTo can run
    // for as long as pages keep resolving, and every frame of that loop drags
    // the reader back to where they left off while they are trying to read.
    final outOfFrames = ++_restoreFrames >= _maxRestoreFrames;

    if (reachedTarget || stoppedGrowing || outOfFrames) {
      _scrollController.jumpTo(target.clamp(0.0, maxExtent));
      _pendingRestoreOffset = null;
      _initialScrollApplied = true;
      _handleScroll();
      return;
    }

    // Still growing and not yet there: jump as far as we can now to force more
    // pages to lay out, then re-check next frame.
    _lastRestoreMaxExtent = maxExtent;
    _scrollController.jumpTo(target.clamp(0.0, maxExtent));
    WidgetsBinding.instance.addPostFrameCallback((_) => _attemptRestoreJump());
  }

  // ── Page extents ──────────────────────────────────────────────────────────

  /// A page has reported its real size. Fold it in when it is safe to touch the
  /// scroll position — never during build or layout, where a correction would
  /// assert.
  void _handleExtentSubmission() {
    if (!mounted || _extentCommitScheduled) return;
    if (_pageExtents.pendingRatios.isEmpty) return;
    _extentCommitScheduled = true;
    final phase = SchedulerBinding.instance.schedulerPhase;
    if (phase == SchedulerPhase.idle ||
        phase == SchedulerPhase.postFrameCallbacks) {
      _commitPageExtents();
    } else {
      WidgetsBinding.instance.addPostFrameCallback((_) => _commitPageExtents());
    }
  }

  /// Apply measured page sizes and undo the shove they give the pages below.
  ///
  /// Both halves land before the next layout, so the list is never laid out with
  /// the new extents and the old offset — that in-between state *is* the jump
  /// the reader sees. Corrections are computed against the pre-commit geometry
  /// for every pending page at once: a page growing above the viewport moves the
  /// pages after it and the viewport itself by the same amount, so their
  /// relative positions stay valid across the batch.
  void _commitPageExtents() {
    _extentCommitScheduled = false;
    if (!mounted || _pageExtents.pendingRatios.isEmpty) return;

    final pending = Map<int, double>.of(_pageExtents.pendingRatios);
    final metrics = _metrics;
    final hasClients = _scrollController.hasClients;
    final scrollOffset =
        hasClients ? _scrollController.position.pixels : 0.0;

    var correction = 0.0;
    if (hasClients) {
      for (final index in pending.keys.toList()..sort()) {
        correction += scrollCorrectionForExtentChange(
          pageStart: metrics.offsetToPage(index + 1),
          oldExtent: metrics.extentAt(index),
          newExtent: metrics.extentForRatio(pending[index]!),
          scrollOffset: scrollOffset,
        );
      }
    }

    setState(() {
      _pageExtents.commitPending();
      _cachedMetrics = null;
    });
    _scrollController.applyExtentCorrection(correction);

    // Deferred: maxScrollExtent still describes the old geometry until the
    // frame this setState schedules has laid out, and reading edge state off it
    // now could spuriously report the end of the chapter.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _handleScroll();
    });
  }

  void _handleScroll() {
    if (!_scrollController.hasClients) return;

    final defaults = _defaults;
    final position = _scrollController.position;
    final maxScroll = position.maxScrollExtent;
    final scrollOffset = position.pixels;
    final viewport = position.viewportDimension;
    final atStart = isAtReadingStart(
      scrollOffset: scrollOffset,
      viewport: viewport,
      maxScroll: maxScroll,
      direction: defaults.direction,
    );
    final atEnd = isAtReadingEnd(
      scrollOffset: scrollOffset,
      viewport: viewport,
      maxScroll: maxScroll,
      direction: defaults.direction,
    );

    // Derived from the same extents the list is laid out with, so the counter,
    // the scrubber and the pages can never drift apart.
    final flatPage = _metrics.pageAtOffset(scrollOffset);
    final feedPosition = _positionAt(flatPage - 1);

    // Update ValueNotifiers — no setState, no rebuild
    _positionNotifier.value = feedPosition;

    // Push edge-state via ValueNotifier — zero setState, zero page-list rebuild
    if (_atStartNotifier.value != atStart) _atStartNotifier.value = atStart;
    if (_atEndNotifier.value != atEnd) _atEndNotifier.value = atEnd;

    _scheduleProgressSave(feedPosition);
    _scheduleScrollSave(scrollOffset, feedPosition);
    _maybeAutoNextChapter(atEnd);
    _maybeExtendFeed(feedPosition);
    _prefetchUpcoming(flatPage);
  }

  /// Ask for the adjacent chapter while there is still reading left between
  /// here and the seam (spec R1: "prefetched before the seam is reached so it
  /// never stalls").
  ///
  /// Both directions, because a boundary you can only cross one way is a trap:
  /// scrolling back up into the chapter just finished has to work as well as
  /// scrolling down out of it.
  void _maybeExtendFeed(ReaderFeedPosition position) {
    final feed = widget.feed;
    final onEnd = widget.onReachedFeedEnd;
    if (onEnd != null &&
        !_loadingNext &&
        feed.length - position.flatIndex <= kSeamPrefetchPages) {
      _loadingNext = true;
      unawaited(onEnd().whenComplete(() => _loadingNext = false));
    }

    final onStart = widget.onReachedFeedStart;
    if (onStart != null &&
        !_loadingPrevious &&
        position.flatIndex <= kSeamPrefetchPages) {
      _loadingPrevious = true;
      unawaited(onStart().whenComplete(() => _loadingPrevious = false));
    }
  }

  /// Warm the next few pages' decoded bitmaps ahead of the visible page so fast
  /// scrolling stays smooth. Uses the same [ResizeImage] key as the rendered
  /// page, so a prefetched page is a cache hit (no re-decode) when it scrolls
  /// into view. Monotonic — never re-warms pages already requested.
  void _prefetchUpcoming(int visiblePage) {
    if (!mounted) return;
    final pages = widget.feed.pages;
    final target = (visiblePage + readerPrefetchAhead).clamp(0, pages.length);
    if (target <= _prefetchedThrough) return;

    final decodeWidth = readerDecodeWidth(
      _containerWidth,
      MediaQuery.devicePixelRatioOf(context),
    );
    final headers = apiImageHttpHeaders(
      ref.read(authTokenStoreProvider).token,
      profileId: ref.read(activeProfileProvider)?.id,
    );
    for (var i = _prefetchedThrough; i < target; i++) {
      final provider = ResizeImage.resizeIfNeeded(
        decodeWidth,
        null,
        CachedNetworkImageProvider(
          pages[i].imageUrl,
          headers: headers,
        ),
      );
      // Fire and forget; swallow errors so a bad page never crashes reading.
      precacheImage(provider, context, onError: (_, __) {});
    }
    _prefetchedThrough = target;
  }

  void _scheduleScrollSave(double scrollTop, ReaderFeedPosition position) {
    // While a deferred restore is still homing in on the saved offset, the
    // controller sits at a clamped-short interim position. Persisting it would
    // overwrite the very offset we are trying to restore, so hold off until the
    // restore has landed.
    if (_pendingRestoreOffset != null) return;
    // The saved offset belongs to the chapter this reader was opened at. Once
    // the reader has scrolled on into a later chapter, that chapter's own
    // reading progress is the resume point and an offset measured across a
    // seam would mean nothing on a feed rebuilt from one chapter.
    if (position.chapterIndex != _anchorIndex) return;
    final relative = scrollTop - _anchorOrigin + readerListLeadingPadding;
    _scrollSaveTimer?.cancel();
    _scrollSaveTimer = Timer(const Duration(milliseconds: _scrollSaveMs), () {
      final prefs = _prefs;
      if (prefs == null) return;
      writeReaderScrollPositionByKey(
        prefs,
        _scrollKey,
        relative < 0 ? 0 : relative,
      );
    });
  }

  void _scheduleProgressSave(ReaderFeedPosition position) {
    if (widget.onSaveProgress == null || widget.feed.isEmpty) return;
    final chapter = widget.feed.chapters[position.chapterIndex];
    _pending = (chapter, position.page);
    _progressSaveTimer?.cancel();
    _progressSaveTimer =
        Timer(const Duration(milliseconds: _progressSaveMs), () {
      _persistProgress(chapter, position.page);
    });
  }

  void _flushProgress() {
    if (widget.onSaveProgress == null) return;
    _progressSaveTimer?.cancel();
    final pending = _pending;
    if (pending == null) return;
    if (_lastSaved == (pending.$1.id, pending.$2)) return;
    _persistProgress(pending.$1, pending.$2);
  }

  /// Saves [page] against [chapter], not against the feed.
  ///
  /// The de-duplication key is the pair: reading forwards out of chapter 5
  /// page 20 into chapter 6 page 1 must save both, and a page-number-only
  /// guard would have swallowed the second time the reader crossed a seam
  /// onto a page number it had already been on.
  Future<void> _persistProgress(ReaderChapter chapter, int page) async {
    final save = widget.onSaveProgress;
    if (save == null) return;
    if (page <= 0 || _lastSaved == (chapter.id, page)) return;
    _lastSaved = (chapter.id, page);
    await save(chapter, page);
  }

  void _maybeAutoNextChapter(bool atEnd) {
    // In a continuous feed the seam IS the mechanism: reaching the end of a
    // chapter scrolls into the next one, and navigating on top of that would
    // be the transition the feed exists to remove. Reaching the end of the
    // FEED with nothing left to load leaves the edge prompt, which is the
    // honest affordance for a boundary that could not be absorbed.
    if (widget.onReachedFeedEnd != null) {
      _autoNextTimer?.cancel();
      _autoNextTimer = null;
      return;
    }
    if (!_defaults.autoNextChapter ||
        !atEnd ||
        widget.onNextChapter == null ||
        _autoNextTriggered) {
      _autoNextTimer?.cancel();
      _autoNextTimer = null;
      return;
    }

    if (_autoNextTimer != null) return;

    _autoNextTimer =
        Timer(const Duration(milliseconds: _autoNextChapterMs), () {
      if (!mounted || _autoNextTriggered) return;
      _autoNextTriggered = true;
      _haptics.selection();
      widget.onNextChapter?.call();
    });
  }

  // ── Auto-scroll ───────────────────────────────────────────────────────────

  void _startAutoScroll() {
    if (_autoScrollActive) return;
    _autoScrollActive = true;
    _lastAutoScrollFrame = null;
    _scheduleAutoScrollFrame();
  }

  void _stopAutoScroll() {
    _autoScrollActive = false;
    _lastAutoScrollFrame = null;
  }

  void _scheduleAutoScrollFrame() {
    if (!_autoScrollActive || !mounted) return;
    WidgetsBinding.instance.addPostFrameCallback((timeStamp) {
      if (!_autoScrollActive || !mounted || !_scrollController.hasClients) {
        return;
      }
      final previous = _lastAutoScrollFrame;
      _lastAutoScrollFrame = timeStamp;
      // The first frame only establishes a baseline timestamp; movement starts
      // on the next one so speed is driven by the real elapsed frame time.
      if (previous == null) {
        _scheduleAutoScrollFrame();
        return;
      }
      final dtSeconds = (timeStamp - previous).inMicroseconds / 1e6;
      final speed = ref.read(readerUiProvider).autoScrollSpeed;
      final pos = _scrollController.position;
      final target = pos.pixels + autoScrollFrameDelta(speed, dtSeconds);
      if (target >= pos.maxScrollExtent) {
        _scrollController.jumpTo(pos.maxScrollExtent);
        _stopAutoScroll();
        ref.read(readerUiProvider.notifier).stopAutoScroll();
        return;
      }
      _scrollController.jumpTo(target);
      _scheduleAutoScrollFrame();
    });
  }

  // ── Controls visibility ───────────────────────────────────────────────────

  void _showControls() {
    ref.read(readerUiProvider.notifier).setControlsVisible(true);
    _scheduleHideControls();
  }

  void _hideControls() {
    ref.read(readerUiProvider.notifier).setControlsVisible(false);
    _hideControlsTimer?.cancel();
  }

  void _scheduleHideControls() {
    _hideControlsTimer?.cancel();
    // How long the bars stay up is the design preset's call: Cinema retires
    // them in 1.2s so the page owns the screen, everything else keeps the 3s
    // the reader has always used.
    _hideControlsTimer = Timer(
      context.readerChrome.autoHideAfter,
      () {
        if (mounted) {
          ref.read(readerUiProvider.notifier).setControlsVisible(false);
        }
      },
    );
  }

  // ── Tap handling ──────────────────────────────────────────────────────────

  void _handleTapDown(TapDownDetails details) {
    _tapDownPosition = details.localPosition;
  }

  void _handleTap() {
    final pos = _tapDownPosition;
    if (pos == null) return;

    // Ignore if we're scrolling or within the cooldown after a scroll ends
    final sinceLastScroll =
        DateTime.now().difference(_lastScrollEnd).inMilliseconds;
    if (_isScrolling || sinceLastScroll < _postScrollCooldownMs) return;

    final width = _containerWidth ?? 400.0;
    final height = _containerHeight ?? 800.0;
    final ui = ref.read(readerUiProvider);

    // Lock mode: count consecutive centre taps; 5 within 2s unlocks. Edge
    // taps are ignored so paging never happens while locked.
    if (ui.isLocked) {
      final isCenterTap = pos.dx > width * 0.2 &&
          pos.dx < width * 0.8 &&
          pos.dy > height * 0.15 &&
          pos.dy < height * 0.85;
      if (!isCenterTap) return;

      final now = DateTime.now();
      if (now.difference(_lastCenterTapTime).inMilliseconds > 2000) {
        _consecutiveCenterTaps = 0;
      }
      _consecutiveCenterTaps++;
      _lastCenterTapTime = now;

      if (_consecutiveCenterTaps >= 5) {
        ref.read(readerUiProvider.notifier).setLocked(false);
        _haptics.medium();
        _consecutiveCenterTaps = 0;
        if (mounted && context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Reader unlocked'),
              duration: Duration(seconds: 2),
              behavior: SnackBarBehavior.floating,
            ),
          );
        }
      }
      return;
    }

    _consecutiveCenterTaps = 0;

    // Double-tap → zoom. Detected manually via timestamps rather than
    // GestureDetector.onDoubleTap, which would add a ~300ms disambiguation
    // delay to every control-button tap and kill the smooth feel.
    final now = DateTime.now();
    if (now.difference(_lastTapTime).inMilliseconds < _doubleTapMs) {
      _lastTapTime = DateTime.fromMillisecondsSinceEpoch(0);
      _haptics.light();
      ref.read(readerUiProvider.notifier).toggleDoubleTapZoom();
      return;
    }
    _lastTapTime = now;

    // Any tap while controls are visible just dismisses them.
    if (ui.controlsVisible) {
      _hideControls();
      return;
    }

    // Controls hidden → tap zones: left/right thirds page, centre reveals
    // controls. Makes the reader usable one-handed.
    if (pos.dx < width * 0.33) {
      _pageBy(forward: false);
    } else if (pos.dx > width * 0.67) {
      _pageBy(forward: true);
    } else {
      _showControls();
    }
  }

  /// Jump to the start of [page].
  ///
  /// Resolved through the same [ReaderPageMetrics] the list is laid out from, so
  /// the scrubber lands exactly where the page counter says it will — a second
  /// estimator here would put the two a page apart on any chapter whose sizes
  /// are not all known yet.
  void _seekToPage(int page) {
    if (!_scrollController.hasClients) return;
    // A restore still homing in would drag the reader straight back off the
    // page they just asked for.
    _abandonPendingRestore();
    final position = _scrollController.position;
    // The scrub rail spans the chapter on screen, not the whole feed — so the
    // page it hands over is chapter-local and has to be placed back into feed
    // coordinates before the geometry can resolve it.
    final flat = widget.feed.startOfChapter(
          _positionNotifier.value.chapterIndex,
        ) +
        page -
        1;
    final target = _metrics.offsetToPage(flat + 1);
    _scrollController.jumpTo(target.clamp(0.0, position.maxScrollExtent));
    // Scrubbing is deliberate interaction with the controls, so keep them up
    // instead of letting the auto-hide close the bar mid-drag.
    _scheduleHideControls();
  }

  /// Animate one viewport (~85%) forward or backward along the reading axis.
  void _pageBy({required bool forward}) {
    if (!_scrollController.hasClients) return;
    _haptics.selection();
    final position = _scrollController.position;
    final delta = position.viewportDimension * 0.85 * (forward ? 1 : -1);
    final target =
        (position.pixels + delta).clamp(0.0, position.maxScrollExtent);
    _scrollController.animateTo(
      target,
      duration: const Duration(milliseconds: 240),
      curve: Curves.easeOutCubic,
    );
  }

  bool _onScrollNotification(ScrollNotification notification) {
    if (notification is ScrollStartNotification &&
        notification.dragDetails != null) {
      _isScrolling = true;
      // The reader has taken over. Abandon a restore that is still homing in
      // rather than yanking them back to the saved offset mid-drag.
      _abandonPendingRestore();
      // Hide controls when the user starts dragging
      if (ref.read(readerUiProvider).controlsVisible) {
        _hideControls();
      }
    } else if (notification is ScrollEndNotification) {
      _isScrolling = false;
      _lastScrollEnd = DateTime.now();
    }
    return false;
  }

  // ── Bookmark ──────────────────────────────────────────────────────────────

  Future<void> _handleBookmark() async {
    final addBookmark = widget.onAddBookmark;
    if (addBookmark == null || _bookmarkPending || widget.feed.isEmpty) return;
    setState(() => _bookmarkPending = true);
    try {
      final position = _positionNotifier.value;
      final chapter = widget.feed.chapters[position.chapterIndex];
      await _persistProgress(chapter, position.page);
      final success = await addBookmark(chapter, position.page);
      if (!mounted || !success || !context.mounted) return;
      _haptics.light();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Bookmarked page ${position.page}'),
          behavior: SnackBarBehavior.floating,
        ),
      );
    } finally {
      if (mounted) {
        setState(() => _bookmarkPending = false);
      }
    }
  }

  // ── More options sheet ────────────────────────────────────────────────────

  void _showMoreOptions() {
    // Re-arm hide timer so controls stay visible while sheet is open
    _hideControlsTimer?.cancel();
    showModalBottomSheet<void>(
      context: context,
      // Elevated surface (#181818) so the sheet lifts off the reader's near-
      // black page backdrop.
      backgroundColor: context.colors.surfaceElevated,
      // Scroll-controlled so the settings sheet is never clipped and its
      // actions stay reachable regardless of content height.
      isScrollControlled: true,
      // Swipe-down-to-dismiss with a visible grab handle (system back alone was
      // not discoverable). enableDrag defaults to true.
      showDragHandle: true,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(context.radii.xl)),
      ),
      builder: (_) => ReaderMoreSheet(
        onPreviousChapter: widget.onPreviousChapter,
        onNextChapter: widget.onNextChapter,
        onOpenSeries: widget.onOpenSeries,
        onBookmark: (widget.showBookmark &&
                widget.onAddBookmark != null &&
                !_bookmarkPending)
            ? _handleBookmark
            : null,
        showBookmark: widget.showBookmark,
      ),
    ).whenComplete(() {
      // Restart auto-hide once sheet is dismissed
      if (mounted) _scheduleHideControls();
    });
  }

  // ── Page item builder ─────────────────────────────────────────────────────

  Widget _buildPageItem({
    required int index,
    required ReaderPageMetrics metrics,
    required ReaderDefaults defaults,
    required double zoom,
    required double viewportWidth,
    required double viewportHeight,
    required Color backgroundColor,
  }) {
    final feed = widget.feed;
    final page = feed.pages[index];
    final chapter = feed.chapterAt(index);
    final pageNumber = feed.pageWithinChapterAt(index);
    final seamExtent = metrics.leadingInsetAt(index);
    final direction = defaults.direction;
    final fitMode = defaults.fitMode;
    final contentWidthFactor = zoom == 1 ? 1.0 : zoom;
    final maxWidth = zoom <= 1 ? maxContentWidth : double.infinity;

    final pageImage = ReaderPageImage(
      imageUrl: page.imageUrl,
      localFile: page.localFile,
      alt: '${chapter.title} page $pageNumber',
      aspectRatio: metrics.ratioAt(index),
      fitMode: fitMode,
      backgroundColor: backgroundColor,
      layoutAxis: direction.scrollAxis,
      viewportWidth: viewportWidth,
      viewportHeight: viewportHeight,
      priority: index < 2,
      onLoad: _handleScroll,
      // Already-known sizes need no second resolve.
      onIntrinsicSize: _pageExtents.isResolved(index)
          ? null
          : (pixelWidth, pixelHeight) => _pageExtents.submitMeasuredSize(
                index,
                pixelWidth: pixelWidth,
                pixelHeight: pixelHeight,
              ),
    );

    // The list forces each item to the extent [metrics] reserved for it, so the
    // clip only ever matters in the single frame between a page decoding at a
    // size nobody predicted and that size being folded into the layout.
    if (direction.isHorizontal) {
      final pageSlot = SizedBox(
        height: viewportHeight,
        width: metrics.extentAt(index) - readerPagedGap - seamExtent,
        child: pageImage,
      );
      return RepaintBoundary(
        child: ClipRect(
          child: Padding(
            padding: const EdgeInsets.only(right: readerPagedGap),
            child: Align(
              child: seamExtent <= 0
                  ? pageSlot
                  : Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        SizedBox(
                          width: seamExtent,
                          height: viewportHeight,
                          child: ChapterSeam(
                            title: chapter.title,
                            axis: Axis.horizontal,
                          ),
                        ),
                        pageSlot,
                      ],
                    ),
            ),
          ),
        ),
      );
    }

    // Vertical (webtoon) mode: no inter-page padding so pages sit flush
    // edge-to-edge. Any earlier gap rendered the backdrop as a seam between
    // pages; letterboxing now uses the backdrop colour inside the page itself.
    // Top-aligned, so a page that turns out taller than reserved grows
    // downward instead of creeping out of both ends of its slot.
    final pageSlot = Align(
      alignment: Alignment.topCenter,
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: maxWidth),
        child: FractionallySizedBox(
          alignment: Alignment.topCenter,
          widthFactor: contentWidthFactor,
          child: pageImage,
        ),
      ),
    );

    return RepaintBoundary(
      child: ClipRect(
        // The seam rides on the page it precedes rather than being a list item
        // of its own: the geometry already reserved exactly [seamExtent] above
        // this page (see ReaderPageMetrics.leadingInsets), so nothing about the
        // offsets, the counter or the scrub rail has to know a divider exists.
        child: seamExtent <= 0
            ? pageSlot
            : Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SizedBox(
                    height: seamExtent,
                    child: ChapterSeam(title: chapter.title),
                  ),
                  pageSlot,
                ],
              ),
      ),
    );
  }

  // ── Build ─────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    final defaults = ref.watch(readerDefaultsProvider);
    ref.listen<ReaderDefaults>(readerDefaultsProvider, (previous, next) {
      if (previous?.keepScreenAwake != next.keepScreenAwake) {
        unawaited(_syncWakelock(next.keepScreenAwake));
      }
      if ((previous?.autoNextChapter ?? false) && !next.autoNextChapter) {
        _autoNextTimer?.cancel();
        _autoNextTimer = null;
      }
      if (previous?.refreshRate != next.refreshRate) {
        _syncRefreshRate(next.refreshRate);
      }
      if (previous?.volumeKeyNavigation != next.volumeKeyNavigation) {
        unawaited(_syncVolumeKeyNav(next.volumeKeyNavigation));
      }
    });

    // Start or stop auto-scroll when the toggle changes.
    ref.listen<bool>(
      readerUiProvider.select((s) => s.autoScrollEnabled),
      (_, enabled) {
        if (enabled) {
          _startAutoScroll();
        } else {
          _stopAutoScroll();
        }
      },
    );

    // Watch only zoom level — control-visibility changes rebuild _ReaderControlsLayer
    // only, not this widget and its expensive ListView.
    final zoomLevel = ref.watch(readerUiProvider.select((s) => s.zoomLevel));
    final readerBackground =
        ref.watch(readerFilterProvider.select((f) => f.background));
    // Sepia/grayscale tone. ``null`` for Normal so the default path adds no
    // ColorFiltered layer (and therefore no saveLayer) around the page list.
    final toneFilter =
        ref.watch(readerFilterProvider.select((f) => f.colorMode.colorFilter));
    final uiController = ref.read(readerUiProvider.notifier);
    final hasPrevious = widget.onPreviousChapter != null;
    final hasNext = widget.onNextChapter != null;
    // Chapter navigation routed through a haptic tick so every entry point —
    // edge prompt, bottom bar, keyboard shortcut — feels the same.
    final onPreviousChapter = widget.onPreviousChapter == null
        ? null
        : () {
            _haptics.light();
            widget.onPreviousChapter!();
          };
    final onNextChapter = widget.onNextChapter == null
        ? null
        : () {
            _haptics.light();
            widget.onNextChapter!();
          };
    final mediaSize = MediaQuery.sizeOf(context);

    _containerWidth = mediaSize.width;
    _containerHeight = mediaSize.height;

    final direction = defaults.direction;
    // Leading padding is always [readerListLeadingPadding] in *scroll* terms —
    // which for a right-to-left chapter is the right-hand side, because the list
    // is reversed. Getting this the wrong way round would offset every page
    // jump by the difference between the two.
    final listPadding = switch (direction) {
      ReadingDirection.vertical => const EdgeInsets.only(
          top: readerListLeadingPadding,
          bottom: readerListTrailingPadding,
        ),
      ReadingDirection.leftToRight => const EdgeInsets.only(
          left: readerListLeadingPadding,
          right: readerListTrailingPadding,
        ),
      ReadingDirection.rightToLeft => const EdgeInsets.only(
          right: readerListLeadingPadding,
          left: readerListTrailingPadding,
        ),
    };

    final metrics = _cachedMetrics = ReaderPageMetrics.of(
      _pageExtents,
      direction: direction,
      fitMode: defaults.fitMode,
      viewportWidth: mediaSize.width,
      viewportHeight: mediaSize.height,
      zoom: zoomLevel,
      leadingInsets: _seamInsets,
    );
    final pageCount = widget.feed.length;

    // Page list — wrapped in RepaintBoundary so overlay repaints (controls,
    // indicators) never propagate into the image tiles. Optionally wrapped in
    // a single ColorFiltered layer for sepia/grayscale tone.
    //
    // Every item is forced to the extent [metrics] reserved for it rather than
    // being measured after the fact. That is what makes a page's height a
    // decision instead of a surprise: a page whose image has not arrived still
    // occupies exactly the space it will occupy once it has, and the offsets a
    // page jump resolves to are the offsets the list actually uses.
    Widget pageList = RepaintBoundary(
      child: ListView.custom(
        key: ValueKey(
          'reader-list-${direction.name}-${defaults.fitMode.name}',
        ),
        controller: _scrollController,
        scrollDirection: direction.scrollAxis,
        reverse: direction.reverseScroll,
        padding: listPadding,
        // Large pre-build window so pages are laid out and decoded well before
        // they scroll into view — smoother fast scrolls, lower latency (we
        // prioritise this over memory footprint).
        scrollCacheExtent: const ScrollCacheExtent.pixels(6000),
        // ListView.builder derives this from its item count; the .custom
        // constructor does not, and without it a screen reader loses the
        // "page N of M" framing for the list.
        semanticChildCount: pageCount,
        itemExtentBuilder: (index, _) =>
            index < 0 || index >= pageCount ? null : metrics.extentAt(index),
        childrenDelegate: _ReaderPageDelegate(
          childCount: pageCount,
          totalExtent: metrics.totalPagesExtent,
          builder: (context, index) => _buildPageItem(
            index: index,
            metrics: metrics,
            defaults: defaults,
            zoom: zoomLevel,
            viewportWidth: mediaSize.width,
            viewportHeight: mediaSize.height,
            backgroundColor: readerBackground.color,
          ),
        ),
      ),
    );
    if (toneFilter != null) {
      pageList = ColorFiltered(colorFilter: toneFilter, child: pageList);
    }

    return ReaderShortcuts(
      onPreviousChapter: onPreviousChapter ?? () {},
      onNextChapter: onNextChapter ?? () {},
      onBookmark: _handleBookmark,
      onZoomIn: uiController.zoomIn,
      onZoomOut: uiController.zoomOut,
      onZoomReset: uiController.resetZoom,
      child: Scaffold(
        backgroundColor: readerBackground.color,
        body: NotificationListener<ScrollNotification>(
          onNotification: _onScrollNotification,
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTapDown: _handleTapDown,
            onTap: _handleTap,
            child: Stack(
              children: [
                // Animated page backdrop — cross-fades when the reader
                // background (Dark / AMOLED / Paper) changes, so it never
                // hard-cuts behind the letterboxed pages.
                Positioned.fill(
                  child: AnimatedContainer(
                    duration: MediaQuery.disableAnimationsOf(context)
                        ? Duration.zero
                        : const Duration(milliseconds: 300),
                    curve: Curves.easeOut,
                    color: readerBackground.color,
                  ),
                ),
                pageList,
                // iOS has no system back-swipe inside the reader (the route is
                // a fade `CustomTransitionPage`, which bypasses
                // `PageTransitionsTheme`), and an iPhone has no hardware back
                // button — so once the controls auto-hide there is no visible
                // and no gestural way out. Hand the platform gesture back, but
                // only in vertical mode, where nothing else wants horizontal
                // drags. In LTR/RTL mode the page list itself pages on that
                // axis and the strip must not exist at all.
                ReaderEdgeBackGesture(
                  enabled: direction.isVertical &&
                      Theme.of(context).platform == TargetPlatform.iOS,
                  onBack: widget.onBack,
                ),
                // Dim + warmth filter — its own ConsumerWidget so brightness
                // drags repaint only this layer, never the page list.
                const ReaderFilterOverlay(),
                // Controls, edge-prompts, and page indicator live in their own
                // ConsumerWidget so toggling visibility never rebuilds the list.
                _ReaderControlsLayer(
                  direction: direction,
                  hasPrevious: hasPrevious,
                  hasNext: hasNext,
                  atStartNotifier: _atStartNotifier,
                  atEndNotifier: _atEndNotifier,
                  positionNotifier: _positionNotifier,
                  onBack: widget.onBack,
                  onOpenSeries: widget.onOpenSeries,
                  onMoreOptions: _showMoreOptions,
                  onSeekToPage: _seekToPage,
                  onPreviousChapter: onPreviousChapter,
                  onNextChapter: onNextChapter,
                  showBookmark: widget.showBookmark,
                  onBookmark: (widget.showBookmark && widget.onAddBookmark != null)
                      ? _handleBookmark
                      : null,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Page delegate that reports the chapter's exact total extent.
///
/// Left to itself a lazy list extrapolates its scrollable range from the average
/// height of the handful of children it happens to have laid out, so
/// `maxScrollExtent` — and therefore where a page jump or the scrub rail lands —
/// keeps moving as you read. Every page's extent is already known here, so hand
/// over the real sum and the range stops drifting.
class _ReaderPageDelegate extends SliverChildBuilderDelegate {
  _ReaderPageDelegate({
    required NullableIndexedWidgetBuilder builder,
    required int childCount,
    required this.totalExtent,
  }) : super(
          builder,
          childCount: childCount,
          // Each page carries its own RepaintBoundary already.
          addRepaintBoundaries: false,
        );

  final double totalExtent;

  @override
  double? estimateMaxScrollOffset(
    int firstIndex,
    int lastIndex,
    double leadingScrollOffset,
    double trailingScrollOffset,
  ) =>
      totalExtent;
}

// ── Controls overlay (separated so readerUiProvider rebuilds don't hit the list)

class _ReaderControlsLayer extends ConsumerWidget {
  const _ReaderControlsLayer({
    required this.direction,
    required this.hasPrevious,
    required this.hasNext,
    required this.atStartNotifier,
    required this.atEndNotifier,
    required this.positionNotifier,
    required this.onBack,
    required this.onOpenSeries,
    required this.onMoreOptions,
    required this.onSeekToPage,
    required this.showBookmark,
    this.onBookmark,
    this.onPreviousChapter,
    this.onNextChapter,
  });

  final ReadingDirection direction;
  final bool hasPrevious;
  final bool hasNext;
  final ValueNotifier<bool> atStartNotifier;
  final ValueNotifier<bool> atEndNotifier;
  /// Which chapter is on screen and where in it — everything the bars say.
  /// A feed-wide page number would be meaningless ("page 4 of 812") and a
  /// scrub rail spanning three hundred chapters would be unusable, so the
  /// chrome is always about the chapter under the reading line.
  final ValueNotifier<ReaderFeedPosition> positionNotifier;
  final VoidCallback onBack;
  final VoidCallback onOpenSeries;
  final VoidCallback onMoreOptions;
  final ValueChanged<int> onSeekToPage;
  final bool showBookmark;
  final VoidCallback? onBookmark;
  final VoidCallback? onPreviousChapter;
  final VoidCallback? onNextChapter;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ui = ref.watch(readerUiProvider);

    return Stack(
      children: [
        // Previous-chapter edge prompt
        ValueListenableBuilder<bool>(
          valueListenable: atStartNotifier,
          builder: (_, atStart, __) {
            if (!hasPrevious) return const SizedBox.shrink();
            return Positioned(
              top: direction.isVertical ? 0 : null,
              bottom: direction.isVertical ? null : 96,
              left: 0,
              right: direction.isHorizontal ? null : 0,
              child: _AnimatedEdgePrompt(
                visible: atStart,
                child: ChapterEdgePrompt(
                  label: 'Previous chapter',
                  direction: EdgeDirection.previous,
                  onTap: onPreviousChapter!,
                ),
              ),
            );
          },
        ),
        // Next-chapter edge prompt
        ValueListenableBuilder<bool>(
          valueListenable: atEndNotifier,
          builder: (_, atEnd, __) {
            if (!hasNext) return const SizedBox.shrink();
            return Positioned(
              top: direction.isVertical ? null : 96,
              bottom: direction.isVertical ? 96 : null,
              left: direction.isHorizontal ? null : 0,
              right: 0,
              child: _AnimatedEdgePrompt(
                visible: atEnd,
                child: ChapterEdgePrompt(
                  label: 'Next chapter',
                  direction: EdgeDirection.next,
                  onTap: onNextChapter!,
                ),
              ),
            );
          },
        ),
        // Nothing is drawn over the reading area itself: the page counter that
        // used to float there sat on top of the artwork every time the controls
        // hid, which is exactly when the reader is looking at the page.
        // Top bar — back (top-left), title (opens the series), bookmark, settings.
        Align(
          alignment: Alignment.topCenter,
          child: GestureDetector(
            onTap: () {},
            child: ValueListenableBuilder<ReaderFeedPosition>(
              valueListenable: positionNotifier,
              builder: (_, position, __) => ReaderTopBar(
                // Names the chapter being READ, which in a continuous feed is
                // not always the one the reader opened.
                chapterTitle: position.chapterTitle,
                visible: ui.controlsVisible,
                onBack: onBack,
                onOpenSeries: onOpenSeries,
                onSettings: onMoreOptions,
                onBookmark: showBookmark ? onBookmark : null,
              ),
            ),
          ),
        ),
        // Bottom bar — prev/next chapter, page indicator, scrub rail.
        Align(
          alignment: Alignment.bottomCenter,
          child: GestureDetector(
            onTap: () {},
            child: ValueListenableBuilder<ReaderFeedPosition>(
              valueListenable: positionNotifier,
              builder: (_, position, __) => ReaderBottomBar(
                visiblePage: position.page,
                pageCount: position.pageCount,
                direction: direction,
                visible: ui.controlsVisible,
                hasPrevious: hasPrevious,
                hasNext: hasNext,
                onSeekToPage: onSeekToPage,
                onPreviousChapter: onPreviousChapter,
                onNextChapter: onNextChapter,
                onSettings: onMoreOptions,
              ),
            ),
          ),
        ),
      ],
    );
  }
}

/// Fades and gently pops a chapter edge prompt in and out as the reader reaches
/// the start/end of a chapter, instead of letting it appear abruptly.
class _AnimatedEdgePrompt extends StatelessWidget {
  const _AnimatedEdgePrompt({required this.visible, required this.child});

  final bool visible;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final reduceMotion = MediaQuery.disableAnimationsOf(context);
    return IgnorePointer(
      ignoring: !visible,
      child: AnimatedScale(
        scale: visible ? 1.0 : 0.9,
        duration:
            reduceMotion ? Duration.zero : const Duration(milliseconds: 240),
        curve: Curves.easeOutBack,
        child: AnimatedOpacity(
          duration:
              reduceMotion ? Duration.zero : const Duration(milliseconds: 200),
          opacity: visible ? 1.0 : 0.0,
          child: child,
        ),
      ),
    );
  }
}
