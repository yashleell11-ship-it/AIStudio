import 'dart:async';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart' show ScrollCacheExtent;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/core/network/api_image.dart';
import 'package:manhwamaniacs/core/platform/native_bridge.dart';
import 'package:manhwamaniacs/core/platform/system_ui.dart';
import 'package:manhwamaniacs/core/utils/haptics.dart';
import 'package:manhwamaniacs/features/profiles/providers/profiles_providers.dart';
import 'package:manhwamaniacs/features/reader/models/reader_chapter.dart';
import 'package:manhwamaniacs/features/reader/providers/reader_filter_provider.dart';
import 'package:manhwamaniacs/features/reader/providers/reader_ui_provider.dart';
import 'package:manhwamaniacs/features/reader/utils/page_layout.dart';
import 'package:manhwamaniacs/features/reader/utils/reader_display_mode.dart';
import 'package:manhwamaniacs/features/reader/utils/reader_image_cache.dart';
import 'package:manhwamaniacs/features/reader/utils/reader_wakelock.dart';
import 'package:manhwamaniacs/features/reader/utils/scroll_storage.dart';
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
const _controlsAutoHideMs = 3000;

/// Minimum milliseconds after a scroll event before a tap is treated as intentional.
const _postScrollCooldownMs = 300;

/// Max gap between two taps to register a double-tap (zoom toggle).
const _doubleTapMs = 280;

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
/// [ReaderChapter] plus optional callbacks for progress/bookmark saves and
/// chapter navigation. Every reader behaviour (fullscreen, scroll restore,
/// zoom, virtualized page list, cached images, edge prompts, auto-next) lives
/// here exactly once so the two entry points cannot drift.
class ReaderContent extends ConsumerStatefulWidget {
  const ReaderContent({
    super.key,
    required this.chapter,
    required this.scrollStorageKey,
    required this.onBack,
    this.initialPage = 1,
    this.showBookmark = true,
    this.onSaveProgress,
    this.onAddBookmark,
    this.onPreviousChapter,
    this.onNextChapter,
  });

  final ReaderChapter chapter;

  /// Opaque key used to persist/restore per-chapter scroll position.
  /// Local reader passes the chapter id; source reader passes a composite.
  final String scrollStorageKey;
  final int initialPage;
  final bool showBookmark;
  final VoidCallback onBack;

  /// Persist reading progress. Only the local library reader supplies this.
  final Future<void> Function(int page)? onSaveProgress;

  /// Create a bookmark at the visible page. Only the local library reader.
  /// Return ``true`` when the bookmark was saved successfully.
  final Future<bool> Function(int page)? onAddBookmark;

  /// Navigate to the previous/next chapter. ``null`` disables that direction.
  final VoidCallback? onPreviousChapter;
  final VoidCallback? onNextChapter;

  @override
  ConsumerState<ReaderContent> createState() => _ReaderContentState();
}

class _ReaderContentState extends ConsumerState<ReaderContent> {
  late final ScrollController _scrollController;
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
  final _scrollProgressNotifier = ValueNotifier<int>(0);
  final _visiblePageNotifier = ValueNotifier<int>(1);
  final _atStartNotifier = ValueNotifier<bool>(false);
  final _atEndNotifier = ValueNotifier<bool>(false);

  // Only bookmark pending still needs setState (affects Scaffold snackbar path)
  var _bookmarkPending = false;

  // Auto-scroll state
  bool _autoScrollActive = false;
  Duration? _lastAutoScrollFrame;

  var _lastSavedPage = 0;
  var _pendingPage = 0;
  var _initialScrollApplied = false;

  // Deferred scroll-restore state. On a long webtoon the ListView.builder has
  // only laid out the viewport + cache extent on the first frame, so the true
  // maxScrollExtent is far smaller than a deep saved offset. We jump toward the
  // target across successive frames (each jump forces more pages to lay out and
  // grows maxScrollExtent) until we can land on it, and suppress scroll saves in
  // the meantime so a clamped-short interim offset never overwrites the saved one.
  double? _pendingRestoreOffset;
  double _lastRestoreMaxExtent = -1;
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
    _visiblePageNotifier.value =
        widget.initialPage.clamp(1, widget.chapter.pages.length);
    _scrollController = ScrollController()..addListener(_handleScroll);
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
    if (_scrollController.hasClients && _prefs != null) {
      writeReaderScrollPositionByKey(
        _prefs!,
        _scrollKey,
        _scrollController.offset,
      );
    }
    _scrollController.dispose();
    _scrollProgressNotifier.dispose();
    _visiblePageNotifier.dispose();
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

  void _restoreInitialScroll() {
    if (_initialScrollApplied || !_scrollController.hasClients) return;

    final prefs = _resolvedPrefs();
    final zoom = ref.read(readerUiProvider).zoomLevel;
    final defaults = _defaults;
    final width = _containerWidth ?? MediaQuery.sizeOf(context).width;
    final height = _containerHeight ?? MediaQuery.sizeOf(context).height;
    final savedScroll = readReaderScrollPositionByKey(prefs, _scrollKey);
    final targetPage = widget.initialPage.clamp(1, widget.chapter.pages.length);
    final estimatedOffset = estimateScrollOffsetToPage(
      widget.chapter.pages,
      targetPage,
      width,
      zoom,
      scrollAxis: defaults.direction.scrollAxis,
      crossAxisSize: defaults.direction.isVertical ? width : height,
    );
    final initialOffset = resolveInitialScrollTop(
      savedScroll: savedScroll,
      initialPage: targetPage,
      pageCount: widget.chapter.pages.length,
      estimatedOffsetToPage: estimatedOffset,
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
    _attemptRestoreJump();
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
    if (target == null || !mounted || !_scrollController.hasClients) return;

    final maxExtent = _scrollController.position.maxScrollExtent;
    final reachedTarget = maxExtent >= target;
    final stoppedGrowing = maxExtent <= _lastRestoreMaxExtent;

    if (reachedTarget || stoppedGrowing) {
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

  void _handleScroll() {
    if (!_scrollController.hasClients) return;

    final defaults = _defaults;
    final position = _scrollController.position;
    final maxScroll = position.maxScrollExtent;
    final scrollOffset = position.pixels;
    final viewport = position.viewportDimension;
    final progress =
        maxScroll > 0 ? ((scrollOffset / maxScroll) * 100).round() : 100;
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

    final width = _containerWidth ?? MediaQuery.sizeOf(context).width;
    final height = _containerHeight ?? MediaQuery.sizeOf(context).height;
    final zoom = ref.read(readerUiProvider).zoomLevel;
    final page = resolveVisiblePage(
      widget.chapter.pages,
      scrollOffset,
      width,
      zoom,
      scrollAxis: defaults.direction.scrollAxis,
      crossAxisSize: defaults.direction.isVertical ? width : height,
    );

    // Update ValueNotifiers — no setState, no rebuild
    _scrollProgressNotifier.value = progress;
    _visiblePageNotifier.value = page;

    // Push edge-state via ValueNotifier — zero setState, zero page-list rebuild
    if (_atStartNotifier.value != atStart) _atStartNotifier.value = atStart;
    if (_atEndNotifier.value != atEnd) _atEndNotifier.value = atEnd;

    _scheduleProgressSave(page);
    _scheduleScrollSave(scrollOffset);
    _maybeAutoNextChapter(atEnd);
    _prefetchUpcoming(page);
  }

  /// Warm the next few pages' decoded bitmaps ahead of the visible page so fast
  /// scrolling stays smooth. Uses the same [ResizeImage] key as the rendered
  /// page, so a prefetched page is a cache hit (no re-decode) when it scrolls
  /// into view. Monotonic — never re-warms pages already requested.
  void _prefetchUpcoming(int visiblePage) {
    if (!mounted) return;
    final pages = widget.chapter.pages;
    final target = (visiblePage + readerPrefetchAhead).clamp(0, pages.length);
    if (target <= _prefetchedThrough) return;

    final decodeWidth = readerDecodeWidth(
      _containerWidth,
      MediaQuery.devicePixelRatioOf(context),
    );
    final headers = apiImageHttpHeaders(ref.read(authTokenStoreProvider).token);
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

  void _scheduleScrollSave(double scrollTop) {
    // While a deferred restore is still homing in on the saved offset, the
    // controller sits at a clamped-short interim position. Persisting it would
    // overwrite the very offset we are trying to restore, so hold off until the
    // restore has landed.
    if (_pendingRestoreOffset != null) return;
    _scrollSaveTimer?.cancel();
    _scrollSaveTimer = Timer(const Duration(milliseconds: _scrollSaveMs), () {
      final prefs = _prefs;
      if (prefs == null) return;
      writeReaderScrollPositionByKey(
        prefs,
        _scrollKey,
        scrollTop,
      );
    });
  }

  void _scheduleProgressSave(int page) {
    if (widget.onSaveProgress == null) return;
    _pendingPage = page;
    _progressSaveTimer?.cancel();
    _progressSaveTimer =
        Timer(const Duration(milliseconds: _progressSaveMs), () {
      _persistProgress(page);
    });
  }

  void _flushProgress() {
    if (widget.onSaveProgress == null) return;
    _progressSaveTimer?.cancel();
    if (_pendingPage > 0 && _pendingPage != _lastSavedPage) {
      _persistProgress(_pendingPage);
    }
  }

  Future<void> _persistProgress(int page) async {
    final save = widget.onSaveProgress;
    if (save == null) return;
    if (page <= 0 || page == _lastSavedPage) return;
    _lastSavedPage = page;
    await save(page);
  }

  void _maybeAutoNextChapter(bool atEnd) {
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
    _hideControlsTimer = Timer(
      const Duration(milliseconds: _controlsAutoHideMs),
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
    if (addBookmark == null || _bookmarkPending) return;
    setState(() => _bookmarkPending = true);
    try {
      await _persistProgress(_visiblePageNotifier.value);
      final success = await addBookmark(_visiblePageNotifier.value);
      if (!mounted || !success || !context.mounted) return;
      _haptics.light();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Bookmarked page ${_visiblePageNotifier.value}'),
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
      backgroundColor: AppColors.surfaceElevated,
      // Scroll-controlled so the settings sheet is never clipped and its
      // actions stay reachable regardless of content height.
      isScrollControlled: true,
      // Swipe-down-to-dismiss with a visible grab handle (system back alone was
      // not discoverable). enableDrag defaults to true.
      showDragHandle: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(AppRadius.xl)),
      ),
      builder: (_) => ReaderMoreSheet(
        onPreviousChapter: widget.onPreviousChapter,
        onNextChapter: widget.onNextChapter,
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
    required ReaderDefaults defaults,
    required double zoom,
    required double viewportWidth,
    required double viewportHeight,
    required Color backgroundColor,
  }) {
    final page = widget.chapter.pages[index];
    final pageNumber = index + 1;
    final aspectRatio = pageAspectRatio(page);
    final direction = defaults.direction;
    final fitMode = defaults.fitMode;
    final contentWidthFactor = zoom == 1 ? 1.0 : zoom;
    final maxWidth = zoom <= 1 ? maxContentWidth : double.infinity;
    final crossAxisSize = direction.isVertical ? viewportWidth : viewportHeight;

    final pageImage = ReaderPageImage(
      imageUrl: page.imageUrl,
      alt: '${widget.chapter.title} page $pageNumber',
      aspectRatio: aspectRatio,
      fitMode: fitMode,
      backgroundColor: backgroundColor,
      layoutAxis: direction.scrollAxis,
      viewportWidth: viewportWidth,
      viewportHeight: viewportHeight,
      priority: index < 2,
      onLoad: _handleScroll,
    );

    if (direction.isHorizontal) {
      final pageWidth = estimatePageExtent(
        page,
        crossAxisSize,
        zoom,
        Axis.horizontal,
      );
      return RepaintBoundary(
        child: Padding(
          padding: const EdgeInsets.only(right: AppSpacing.xs),
          child: Align(
            child: SizedBox(
              height: crossAxisSize,
              width: pageWidth * contentWidthFactor,
              child: pageImage,
            ),
          ),
        ),
      );
    }

    // Vertical (webtoon) mode: no inter-page padding so pages sit flush
    // edge-to-edge. Any earlier gap rendered the backdrop as a seam between
    // pages; letterboxing now uses the backdrop colour inside the page itself.
    return RepaintBoundary(
      child: Align(
        child: ConstrainedBox(
          constraints: BoxConstraints(maxWidth: maxWidth),
          child: FractionallySizedBox(
            widthFactor: contentWidthFactor,
            child: pageImage,
          ),
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
    final listPadding = direction.isVertical
        ? const EdgeInsets.only(top: AppSpacing.lg, bottom: 120)
        : const EdgeInsets.only(left: AppSpacing.lg, right: 120);

    // Page list — wrapped in RepaintBoundary so overlay repaints (controls,
    // indicators) never propagate into the image tiles. Optionally wrapped in
    // a single ColorFiltered layer for sepia/grayscale tone.
    Widget pageList = RepaintBoundary(
      child: ListView.builder(
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
        addRepaintBoundaries: false, // handled per-item below
        itemCount: widget.chapter.pages.length,
        itemBuilder: (context, index) => _buildPageItem(
          index: index,
          defaults: defaults,
          zoom: zoomLevel,
          viewportWidth: mediaSize.width,
          viewportHeight: mediaSize.height,
          backgroundColor: readerBackground.color,
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
                  chapter: widget.chapter,
                  direction: direction,
                  hasPrevious: hasPrevious,
                  hasNext: hasNext,
                  atStartNotifier: _atStartNotifier,
                  atEndNotifier: _atEndNotifier,
                  scrollProgressNotifier: _scrollProgressNotifier,
                  visiblePageNotifier: _visiblePageNotifier,
                  onBack: widget.onBack,
                  onMoreOptions: _showMoreOptions,
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

// ── Controls overlay (separated so readerUiProvider rebuilds don't hit the list)

class _ReaderControlsLayer extends ConsumerWidget {
  const _ReaderControlsLayer({
    required this.chapter,
    required this.direction,
    required this.hasPrevious,
    required this.hasNext,
    required this.atStartNotifier,
    required this.atEndNotifier,
    required this.scrollProgressNotifier,
    required this.visiblePageNotifier,
    required this.onBack,
    required this.onMoreOptions,
    required this.showBookmark,
    this.onBookmark,
    this.onPreviousChapter,
    this.onNextChapter,
  });

  final ReaderChapter chapter;
  final ReadingDirection direction;
  final bool hasPrevious;
  final bool hasNext;
  final ValueNotifier<bool> atStartNotifier;
  final ValueNotifier<bool> atEndNotifier;
  final ValueNotifier<int> scrollProgressNotifier;
  final ValueNotifier<int> visiblePageNotifier;
  final VoidCallback onBack;
  final VoidCallback onMoreOptions;
  final bool showBookmark;
  final VoidCallback? onBookmark;
  final VoidCallback? onPreviousChapter;
  final VoidCallback? onNextChapter;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ui = ref.watch(readerUiProvider);
    final pageCount = chapter.pages.length;

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
        // Minimal page indicator (visible when controls are hidden)
        ValueListenableBuilder<int>(
          valueListenable: visiblePageNotifier,
          builder: (_, page, __) => ReaderPageIndicator(
            visiblePage: page,
            pageCount: pageCount,
            visible: ui.controlsVisible,
          ),
        ),
        // Top bar — back (top-left), title, bookmark, settings.
        Align(
          alignment: Alignment.topCenter,
          child: GestureDetector(
            onTap: () {},
            child: ReaderTopBar(
              chapterTitle: chapter.title,
              visible: ui.controlsVisible,
              onBack: onBack,
              onSettings: onMoreOptions,
              onBookmark: showBookmark ? onBookmark : null,
            ),
          ),
        ),
        // Bottom bar — prev/next chapter, progress, page indicator.
        Align(
          alignment: Alignment.bottomCenter,
          child: GestureDetector(
            onTap: () {},
            child: ValueListenableBuilder<int>(
              valueListenable: scrollProgressNotifier,
              builder: (_, progress, __) => ValueListenableBuilder<int>(
                valueListenable: visiblePageNotifier,
                builder: (_, page, __) => ReaderBottomBar(
                  visiblePage: page,
                  pageCount: pageCount,
                  scrollProgress: progress,
                  visible: ui.controlsVisible,
                  hasPrevious: hasPrevious,
                  hasNext: hasNext,
                  onPreviousChapter: onPreviousChapter,
                  onNextChapter: onNextChapter,
                  onSettings: onMoreOptions,
                ),
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
