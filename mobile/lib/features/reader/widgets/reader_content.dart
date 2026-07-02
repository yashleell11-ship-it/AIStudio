import 'dart:async';

import 'package:aistudio_mobile/app/theme/app_colors.dart';
import 'package:aistudio_mobile/app/theme/app_spacing.dart';
import 'package:aistudio_mobile/features/reader/models/reader_chapter.dart';
import 'package:aistudio_mobile/features/reader/providers/reader_ui_provider.dart';
import 'package:aistudio_mobile/features/reader/utils/page_layout.dart';
import 'package:aistudio_mobile/features/reader/utils/reader_wakelock.dart';
import 'package:aistudio_mobile/features/reader/utils/scroll_storage.dart';
import 'package:aistudio_mobile/features/reader/widgets/reader_controls.dart';
import 'package:aistudio_mobile/features/reader/widgets/reader_page_image.dart';
import 'package:aistudio_mobile/features/reader/widgets/reader_shortcuts.dart';
import 'package:aistudio_mobile/features/settings/models/reader_defaults.dart';
import 'package:aistudio_mobile/features/settings/providers/settings_provider.dart';
import 'package:aistudio_mobile/shared/providers/core_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _scrollSaveMs = 250;
const _progressSaveMs = 500;
const _autoNextChapterMs = 900;

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
  Timer? _scrollSaveTimer;
  Timer? _progressSaveTimer;
  Timer? _autoNextTimer;
  var _lastSavedPage = 0;
  var _pendingPage = 0;
  var _visiblePage = 1;
  var _scrollProgress = 0;
  var _atReadingStart = false;
  var _atReadingEnd = false;
  var _bookmarkPending = false;
  var _initialScrollApplied = false;
  var _autoNextTriggered = false;
  var _wakelockEnabled = false;
  double? _containerWidth;
  double? _containerHeight;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _prefs ??= ref.read(sharedPrefsProvider);
    _wakelock ??= ref.read(readerWakelockProvider);
  }

  @override
  void initState() {
    super.initState();
    _visiblePage = widget.initialPage.clamp(1, widget.chapter.pages.length);
    _scrollController = ScrollController()..addListener(_handleScroll);
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _restoreInitialScroll();
      _syncWakelock(ref.read(readerDefaultsProvider).keepScreenAwake);
    });
  }

  @override
  void dispose() {
    _flushProgress();
    _scrollSaveTimer?.cancel();
    _progressSaveTimer?.cancel();
    _autoNextTimer?.cancel();
    _autoNextTimer = null;
    unawaited(_releaseWakelock());
    if (_scrollController.hasClients && _prefs != null) {
      writeReaderScrollPositionByKey(
        _prefs!,
        widget.scrollStorageKey,
        _scrollController.offset,
      );
    }
    _scrollController.dispose();
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    super.dispose();
  }

  SharedPreferences _resolvedPrefs() => _prefs ?? ref.read(sharedPrefsProvider);

  ReaderDefaults get _defaults => ref.read(readerDefaultsProvider);

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

  Future<void> _releaseWakelock() async {
    if (!_wakelockEnabled) return;
    await _wakelock?.disable();
    _wakelockEnabled = false;
  }

  void _restoreInitialScroll() {
    if (_initialScrollApplied || !_scrollController.hasClients) return;

    final prefs = _resolvedPrefs();
    final zoom = ref.read(readerUiProvider).zoomLevel;
    final defaults = _defaults;
    final width = _containerWidth ?? MediaQuery.sizeOf(context).width;
    final height = _containerHeight ?? MediaQuery.sizeOf(context).height;
    final savedScroll =
        readReaderScrollPositionByKey(prefs, widget.scrollStorageKey);
    final targetPage =
        widget.initialPage.clamp(1, widget.chapter.pages.length);
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

    if (initialOffset > 0) {
      _scrollController.jumpTo(initialOffset.clamp(
        0,
        _scrollController.position.maxScrollExtent,
      ));
    }
    _initialScrollApplied = true;
    _handleScroll();
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

    setState(() {
      _scrollProgress = progress;
      _atReadingStart = atStart;
      _atReadingEnd = atEnd;
      _visiblePage = page;
    });

    _scheduleProgressSave(page);
    _scheduleScrollSave(scrollOffset);
    _maybeAutoNextChapter(atEnd);
  }

  void _scheduleScrollSave(double scrollTop) {
    _scrollSaveTimer?.cancel();
    _scrollSaveTimer = Timer(const Duration(milliseconds: _scrollSaveMs), () {
      final prefs = _prefs;
      if (prefs == null) return;
      writeReaderScrollPositionByKey(
        prefs,
        widget.scrollStorageKey,
        scrollTop,
      );
    });
  }

  void _scheduleProgressSave(int page) {
    if (widget.onSaveProgress == null) return;
    _pendingPage = page;
    _progressSaveTimer?.cancel();
    _progressSaveTimer = Timer(const Duration(milliseconds: _progressSaveMs), () {
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

    _autoNextTimer = Timer(const Duration(milliseconds: _autoNextChapterMs), () {
      if (!mounted || _autoNextTriggered) return;
      _autoNextTriggered = true;
      widget.onNextChapter?.call();
    });
  }

  Future<void> _handleBookmark() async {
    final addBookmark = widget.onAddBookmark;
    if (addBookmark == null || _bookmarkPending) return;
    setState(() => _bookmarkPending = true);
    try {
      await _persistProgress(_visiblePage);
      final success = await addBookmark(_visiblePage);
      if (!mounted || !success || !context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Bookmarked page $_visiblePage'),
          behavior: SnackBarBehavior.floating,
        ),
      );
    } finally {
      if (mounted) {
        setState(() => _bookmarkPending = false);
      }
    }
  }

  Widget _buildPageItem({
    required int index,
    required ReaderDefaults defaults,
    required double zoom,
    required double viewportWidth,
    required double viewportHeight,
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
      return Padding(
        padding: const EdgeInsets.only(right: AppSpacing.xs),
        child: Align(
          alignment: Alignment.center,
          child: SizedBox(
            height: crossAxisSize,
            width: pageWidth * contentWidthFactor,
            child: pageImage,
          ),
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.xs),
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

  @override
  Widget build(BuildContext context) {
    final defaults = ref.watch(readerDefaultsProvider);
    ref.listen<ReaderDefaults>(readerDefaultsProvider, (previous, next) {
      if (previous?.keepScreenAwake != next.keepScreenAwake) {
        unawaited(_syncWakelock(next.keepScreenAwake));
      }
      if (previous?.autoNextChapter == true && !next.autoNextChapter) {
        _autoNextTimer?.cancel();
        _autoNextTimer = null;
      }
    });

    final ui = ref.watch(readerUiProvider);
    final uiController = ref.read(readerUiProvider.notifier);
    final hasPrevious = widget.onPreviousChapter != null;
    final hasNext = widget.onNextChapter != null;
    final mediaSize = MediaQuery.sizeOf(context);

    _containerWidth = mediaSize.width;
    _containerHeight = mediaSize.height;

    final direction = defaults.direction;
    final listPadding = direction.isVertical
        ? const EdgeInsets.only(top: AppSpacing.lg, bottom: 120)
        : const EdgeInsets.only(left: AppSpacing.lg, right: 120);

    return ReaderShortcuts(
      onPreviousChapter:
          hasPrevious ? widget.onPreviousChapter! : () {},
      onNextChapter: hasNext ? widget.onNextChapter! : () {},
      onBookmark: _handleBookmark,
      onZoomIn: uiController.zoomIn,
      onZoomOut: uiController.zoomOut,
      onZoomReset: uiController.resetZoom,
      child: Scaffold(
        backgroundColor: AppColors.bg,
        body: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: uiController.toggleControls,
          child: Stack(
            children: [
              ListView.builder(
                key: ValueKey('reader-list-${direction.name}-${defaults.fitMode.name}'),
                controller: _scrollController,
                scrollDirection: direction.scrollAxis,
                reverse: direction.reverseScroll,
                padding: listPadding,
                cacheExtent: 2400,
                itemCount: widget.chapter.pages.length,
                itemBuilder: (context, index) => _buildPageItem(
                  index: index,
                  defaults: defaults,
                  zoom: ui.zoomLevel,
                  viewportWidth: mediaSize.width,
                  viewportHeight: mediaSize.height,
                ),
              ),
              if (_atReadingStart && hasPrevious)
                Positioned(
                  top: direction.isVertical ? 0 : null,
                  bottom: direction.isVertical ? null : 96,
                  left: direction.isHorizontal ? 0 : 0,
                  right: direction.isHorizontal ? null : 0,
                  child: ChapterEdgePrompt(
                    label: 'Previous chapter',
                    direction: EdgeDirection.previous,
                    onTap: widget.onPreviousChapter!,
                  ),
                ),
              if (_atReadingEnd && hasNext)
                Positioned(
                  top: direction.isVertical ? null : 96,
                  bottom: direction.isVertical ? 96 : null,
                  left: direction.isHorizontal ? null : 0,
                  right: direction.isHorizontal ? 0 : 0,
                  child: ChapterEdgePrompt(
                    label: 'Next chapter',
                    direction: EdgeDirection.next,
                    onTap: widget.onNextChapter!,
                  ),
                ),
              ReaderPageIndicator(
                visiblePage: _visiblePage,
                pageCount: widget.chapter.pages.length,
                visible: ui.controlsVisible,
              ),
              Positioned.fill(
                child: Align(
                  alignment: Alignment.bottomCenter,
                  child: GestureDetector(
                    onTap: () {},
                    child: ReaderControlsBar(
                      chapterTitle: widget.chapter.title,
                      scrollProgress: _scrollProgress,
                      visiblePage: _visiblePage,
                      pageCount: widget.chapter.pages.length,
                      zoom: ui.zoomLevel,
                      visible: ui.controlsVisible,
                      onZoomIn: uiController.zoomIn,
                      onZoomOut: uiController.zoomOut,
                      onZoomReset: uiController.resetZoom,
                      onBack: widget.onBack,
                      onPreviousChapter: widget.onPreviousChapter,
                      onNextChapter: widget.onNextChapter,
                      onBookmark: widget.onAddBookmark == null ? null : _handleBookmark,
                      bookmarkPending: _bookmarkPending,
                      showBookmark: widget.showBookmark,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
