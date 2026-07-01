import 'dart:async';

import 'package:aistudio_mobile/app/router/routes.dart';
import 'package:aistudio_mobile/app/theme/app_colors.dart';
import 'package:aistudio_mobile/app/theme/app_spacing.dart';
import 'package:aistudio_mobile/app/theme/app_typography.dart';
import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/features/library/models/chapter.dart';
import 'package:aistudio_mobile/features/library/repositories/library_repository.dart';
import 'package:aistudio_mobile/features/reader/providers/reader_chapter_provider.dart';
import 'package:aistudio_mobile/features/reader/providers/reader_ui_provider.dart';
import 'package:aistudio_mobile/features/reader/utils/page_image_url.dart';
import 'package:aistudio_mobile/features/reader/utils/page_layout.dart';
import 'package:aistudio_mobile/features/reader/utils/scroll_storage.dart';
import 'package:aistudio_mobile/features/reader/widgets/reader_controls.dart';
import 'package:aistudio_mobile/features/reader/widgets/reader_controls.dart';
import 'package:aistudio_mobile/features/reader/widgets/reader_error_state.dart';
import 'package:aistudio_mobile/features/reader/widgets/reader_page_image.dart';
import 'package:aistudio_mobile/features/reader/widgets/reader_shortcuts.dart';
import 'package:aistudio_mobile/features/reader/widgets/reader_skeleton.dart';
import 'package:aistudio_mobile/shared/providers/core_providers.dart';
import 'package:aistudio_mobile/shared/providers/repository_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _scrollEdgeThreshold = 48.0;
const _scrollSaveMs = 250;
const _progressSaveMs = 500;
const _autoNextChapterMs = 900;

class ReaderScreen extends ConsumerStatefulWidget {
  const ReaderScreen({
    super.key,
    required this.seriesId,
    required this.chapterId,
    this.initialPage = 1,
  });

  final int seriesId;
  final int chapterId;
  final int initialPage;

  @override
  ConsumerState<ReaderScreen> createState() => _ReaderScreenState();
}

class _ReaderScreenState extends ConsumerState<ReaderScreen> {
  @override
  Widget build(BuildContext context) {
    final chapterAsync = ref.watch(readerChapterProvider(widget.chapterId));

    return chapterAsync.when(
      loading: () => const ReaderSkeleton(),
      error: (error, _) {
        final appError = error is AppError
            ? error
            : UnknownError(message: error.toString(), cause: error);
        return ReaderErrorState(
          error: appError,
          onRetry: () => ref.invalidate(readerChapterProvider(widget.chapterId)),
          onBack: () => context.pop(),
        );
      },
      data: (chapter) {
        if (chapter.pages.isEmpty) {
          return ColoredBox(
            color: AppColors.bg,
            child: Center(
              child: Text(
                'This chapter has no pages.',
                style: AppTypography.body.copyWith(color: AppColors.muted),
              ),
            ),
          );
        }

        return _ReaderContent(
          seriesId: widget.seriesId,
          chapterId: widget.chapterId,
          chapter: chapter,
          initialPage: widget.initialPage,
        );
      },
    );
  }
}

class _ReaderContent extends ConsumerStatefulWidget {
  const _ReaderContent({
    required this.seriesId,
    required this.chapterId,
    required this.chapter,
    required this.initialPage,
  });

  final int seriesId;
  final int chapterId;
  final ChapterDetail chapter;
  final int initialPage;

  @override
  ConsumerState<_ReaderContent> createState() => _ReaderContentState();
}

class _ReaderContentState extends ConsumerState<_ReaderContent> {
  late final ScrollController _scrollController;
  LibraryRepository? _repository;
  SharedPreferences? _prefs;
  Timer? _scrollSaveTimer;
  Timer? _progressSaveTimer;
  Timer? _autoNextTimer;
  var _lastSavedPage = 0;
  var _pendingPage = 0;
  var _visiblePage = 1;
  var _scrollProgress = 0;
  var _atTop = false;
  var _atBottom = false;
  var _bookmarkPending = false;
  var _initialScrollApplied = false;
  var _autoNextTriggered = false;
  double? _containerWidth;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _repository ??= ref.read(libraryRepositoryProvider);
    _prefs ??= ref.read(sharedPrefsProvider);
  }

  @override
  void initState() {
    super.initState();
    _visiblePage = widget.initialPage.clamp(1, widget.chapter.pages.length);
    _scrollController = ScrollController()..addListener(_handleScroll);
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
    WidgetsBinding.instance.addPostFrameCallback((_) => _restoreInitialScroll());
  }

  @override
  void dispose() {
    _flushProgress();
    _scrollSaveTimer?.cancel();
    _progressSaveTimer?.cancel();
    _autoNextTimer?.cancel();
    if (_scrollController.hasClients && _prefs != null) {
      writeReaderScrollPosition(
        _prefs!,
        widget.chapterId,
        _scrollController.offset,
      );
    }
    _scrollController.dispose();
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    super.dispose();
  }

  SharedPreferences _resolvedPrefs() => _prefs ?? ref.read(sharedPrefsProvider);

  void _restoreInitialScroll() {
    if (_initialScrollApplied || !_scrollController.hasClients) return;

    final prefs = _resolvedPrefs();
    final zoom = ref.read(readerUiProvider).zoomLevel;
    final width = _containerWidth ?? MediaQuery.sizeOf(context).width;
    final savedScroll = readReaderScrollPosition(prefs, widget.chapterId);
    final targetPage =
        widget.initialPage.clamp(1, widget.chapter.pages.length);
    final estimatedOffset = estimateScrollOffsetToPage(
      widget.chapter.pages,
      targetPage,
      width,
      zoom,
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

    final position = _scrollController.position;
    final maxScroll = position.maxScrollExtent;
    final scrollTop = position.pixels;
    final viewport = position.viewportDimension;
    final progress =
        maxScroll > 0 ? ((scrollTop / maxScroll) * 100).round() : 100;
    final atTop = scrollTop <= _scrollEdgeThreshold;
    final atBottom = scrollTop + viewport >= maxScroll - _scrollEdgeThreshold;

    final width = _containerWidth ?? MediaQuery.sizeOf(context).width;
    final zoom = ref.read(readerUiProvider).zoomLevel;
    final page = resolveVisiblePage(
      widget.chapter.pages,
      scrollTop,
      width,
      zoom,
    );

    setState(() {
      _scrollProgress = progress;
      _atTop = atTop;
      _atBottom = atBottom;
      _visiblePage = page;
    });

    _scheduleProgressSave(page);
    _scheduleScrollSave(scrollTop);
    _maybeAutoNextChapter(atBottom);
  }

  void _scheduleScrollSave(double scrollTop) {
    _scrollSaveTimer?.cancel();
    _scrollSaveTimer = Timer(const Duration(milliseconds: _scrollSaveMs), () {
      final prefs = _prefs;
      if (prefs == null) return;
      writeReaderScrollPosition(
        prefs,
        widget.chapterId,
        scrollTop,
      );
    });
  }

  void _scheduleProgressSave(int page) {
    _pendingPage = page;
    _progressSaveTimer?.cancel();
    _progressSaveTimer = Timer(const Duration(milliseconds: _progressSaveMs), () {
      _persistProgress(page);
    });
  }

  void _flushProgress() {
    _progressSaveTimer?.cancel();
    if (_pendingPage > 0 && _pendingPage != _lastSavedPage) {
      _persistProgress(_pendingPage);
    }
  }

  Future<void> _persistProgress(int page) async {
    if (page <= 0 || page == _lastSavedPage) return;
    _lastSavedPage = page;
    final repo = _repository;
    if (repo == null) return;
    await repo.saveProgress(
      seriesId: widget.seriesId,
      chapterId: widget.chapterId,
      lastPage: page,
    );
  }

  void _maybeAutoNextChapter(bool atBottom) {
    final nextAsync = ref.read(
      adjacentChapterProvider((
        chapterId: widget.chapterId,
        direction: 'next',
      )),
    );
    final nextChapter = nextAsync.valueOrNull;
    if (!atBottom || nextChapter == null || _autoNextTriggered) {
      _autoNextTimer?.cancel();
      return;
    }

    _autoNextTimer ??= Timer(const Duration(milliseconds: _autoNextChapterMs), () {
      if (!mounted || _autoNextTriggered) return;
      _autoNextTriggered = true;
      _goToChapter(nextChapter.id);
    });
  }

  Future<void> _handleBookmark() async {
    if (_bookmarkPending) return;
    setState(() => _bookmarkPending = true);
    await _persistProgress(_visiblePage);
    final repo = _repository;
    if (repo == null) return;
    final result = await repo.addBookmark(
      seriesId: widget.seriesId,
      chapterId: widget.chapterId,
      page: _visiblePage,
    );
    if (mounted) {
      setState(() => _bookmarkPending = false);
      if (result.isOk && context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Bookmarked page $_visiblePage'),
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    }
  }

  void _goToChapter(int chapterId) {
    final path = RoutePaths.reader(widget.seriesId, chapterId);
    context.go(path);
  }

  @override
  Widget build(BuildContext context) {
    final ui = ref.watch(readerUiProvider);
    final uiController = ref.read(readerUiProvider.notifier);
    final apiBaseUrl = ref.watch(apiBaseUrlProvider);
    final previousAsync = ref.watch(
      adjacentChapterProvider((
        chapterId: widget.chapterId,
        direction: 'previous',
      )),
    );
    final nextAsync = ref.watch(
      adjacentChapterProvider((
        chapterId: widget.chapterId,
        direction: 'next',
      )),
    );
    final previousChapter = previousAsync.valueOrNull;
    final nextChapter = nextAsync.valueOrNull;

    _containerWidth = MediaQuery.sizeOf(context).width;

    return ReaderShortcuts(
      onPreviousChapter: previousChapter != null
          ? () => _goToChapter(previousChapter.id)
          : () {},
      onNextChapter:
          nextChapter != null ? () => _goToChapter(nextChapter.id) : () {},
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
                controller: _scrollController,
                padding: const EdgeInsets.only(
                  top: AppSpacing.lg,
                  bottom: 120,
                ),
                cacheExtent: 2400,
                itemCount: widget.chapter.pages.length,
                itemBuilder: (context, index) {
                  final page = widget.chapter.pages[index];
                  final pageNumber = index + 1;
                  final aspectRatio = pageAspectRatio(page);
                  final zoom = ui.zoomLevel;
                  final contentWidthFactor = zoom == 1 ? 1.0 : zoom;
                  final maxWidth = zoom <= 1 ? 768.0 : double.infinity;

                  return Padding(
                    padding: const EdgeInsets.only(bottom: AppSpacing.xs),
                    child: Align(
                      child: ConstrainedBox(
                        constraints: BoxConstraints(maxWidth: maxWidth),
                        child: FractionallySizedBox(
                          widthFactor: contentWidthFactor,
                          child: ReaderPageImage(
                            imageUrl: readerPageImageUrl(apiBaseUrl, page.id),
                            alt: '${widget.chapter.title} page $pageNumber',
                            aspectRatio: aspectRatio,
                            priority: index < 2,
                            onLoad: _handleScroll,
                          ),
                        ),
                      ),
                    ),
                  );
                },
              ),
              if (_atTop && previousChapter != null)
                Positioned(
                  top: 0,
                  left: 0,
                  right: 0,
                  child: ChapterEdgePrompt(
                    label: 'Previous chapter',
                    direction: EdgeDirection.previous,
                    onTap: () => _goToChapter(previousChapter.id),
                  ),
                ),
              if (_atBottom && nextChapter != null)
                Positioned(
                  bottom: 96,
                  left: 0,
                  right: 0,
                  child: ChapterEdgePrompt(
                    label: 'Next chapter',
                    direction: EdgeDirection.next,
                    onTap: () => _goToChapter(nextChapter.id),
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
                      onBack: () => context.pop(),
                      onPreviousChapter: previousChapter != null
                          ? () => _goToChapter(previousChapter.id)
                          : null,
                      onNextChapter:
                          nextChapter != null ? () => _goToChapter(nextChapter.id) : null,
                      onBookmark: _handleBookmark,
                      bookmarkPending: _bookmarkPending,
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
