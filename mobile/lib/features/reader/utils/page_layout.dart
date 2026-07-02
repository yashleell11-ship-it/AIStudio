import 'package:aistudio_mobile/features/reader/models/reader_page.dart';
import 'package:aistudio_mobile/features/settings/models/reader_defaults.dart';
import 'package:flutter/material.dart';

const double defaultContainerWidth = 768;
const double maxContentWidth = 768;
const double defaultAspectRatio = 2 / 3;

BoxFit readerFitModeToBoxFit(ReaderFitMode mode) => switch (mode) {
      ReaderFitMode.width => BoxFit.fitWidth,
      ReaderFitMode.height => BoxFit.fitHeight,
      ReaderFitMode.screen => BoxFit.contain,
    };
double resolveContainerWidth(double measuredWidth) =>
    measuredWidth > 0 ? measuredWidth : defaultContainerWidth;

double estimatePageHeight(
  ReaderPage page,
  double containerWidth,
  double zoom,
) {
  final contentWidth = (containerWidth.clamp(0, maxContentWidth)) * zoom;
  final width = page.width;
  final height = page.height;
  if (width != null && height != null && width > 0) {
    return (contentWidth / width) * height;
  }
  return contentWidth / defaultAspectRatio;
}

double estimatePageWidth(
  ReaderPage page,
  double containerHeight,
  double zoom,
) {
  final contentHeight = containerHeight * zoom;
  final width = page.width;
  final height = page.height;
  if (width != null && height != null && height > 0) {
    return (contentHeight / height) * width;
  }
  return contentHeight * defaultAspectRatio;
}

double estimatePageExtent(
  ReaderPage page,
  double crossAxisSize,
  double zoom,
  Axis scrollAxis,
) =>
    scrollAxis == Axis.vertical
        ? estimatePageHeight(page, crossAxisSize, zoom)
        : estimatePageWidth(page, crossAxisSize, zoom);

double pageAspectRatio(ReaderPage page) {
  final width = page.width;
  final height = page.height;
  if (width != null && height != null && width > 0 && height > 0) {
    return width / height;
  }
  return defaultAspectRatio;
}

double estimateScrollOffsetToPage(
  List<ReaderPage> pages,
  int pageNumber,
  double containerWidth,
  double zoom, {
  Axis scrollAxis = Axis.vertical,
  double crossAxisSize = defaultContainerWidth,
}) {
  final targetIndex = (pageNumber - 1).clamp(0, pages.length - 1);
  var offset = 0.0;
  for (var index = 0; index < targetIndex; index++) {
    offset += estimatePageExtent(
      pages[index],
      scrollAxis == Axis.vertical ? containerWidth : crossAxisSize,
      zoom,
      scrollAxis,
    );
  }
  return offset;
}

int resolveVisiblePage(
  List<ReaderPage> pages,
  double scrollOffset,
  double containerWidth,
  double zoom, {
  Axis scrollAxis = Axis.vertical,
  double crossAxisSize = defaultContainerWidth,
}) {
  if (pages.isEmpty) return 1;

  var cumulative = 0.0;
  var activePage = 1;
  for (var index = 0; index < pages.length; index++) {
    final extent = estimatePageExtent(
      pages[index],
      scrollAxis == Axis.vertical ? containerWidth : crossAxisSize,
      zoom,
      scrollAxis,
    );
    if (cumulative <= scrollOffset + 80) {
      activePage = index + 1;
    }
    cumulative += extent;
  }
  return activePage;
}

bool isAtReadingStart({
  required double scrollOffset,
  required double viewport,
  required double maxScroll,
  required ReadingDirection direction,
}) {
  if (direction.isVertical) {
    return scrollOffset <= _scrollEdgeThreshold;
  }

  final atLeft = scrollOffset <= _scrollEdgeThreshold;
  final atRight =
      scrollOffset + viewport >= maxScroll - _scrollEdgeThreshold;
  return switch (direction) {
    ReadingDirection.leftToRight => atLeft,
    ReadingDirection.rightToLeft => atRight,
    ReadingDirection.vertical => atLeft,
  };
}

bool isAtReadingEnd({
  required double scrollOffset,
  required double viewport,
  required double maxScroll,
  required ReadingDirection direction,
}) {
  if (direction.isVertical) {
    return scrollOffset + viewport >= maxScroll - _scrollEdgeThreshold;
  }

  final atLeft = scrollOffset <= _scrollEdgeThreshold;
  final atRight =
      scrollOffset + viewport >= maxScroll - _scrollEdgeThreshold;
  return switch (direction) {
    ReadingDirection.leftToRight => atRight,
    ReadingDirection.rightToLeft => atLeft,
    ReadingDirection.vertical => atRight,
  };
}

const double _scrollEdgeThreshold = 48.0;

double resolveInitialScrollTop({
  required double? savedScroll,
  required int initialPage,
  required int pageCount,
  required double estimatedOffsetToPage,
}) {
  if (savedScroll != null) return savedScroll;
  if (initialPage > 1 && pageCount > 0) return estimatedOffsetToPage;
  return 0;
}
