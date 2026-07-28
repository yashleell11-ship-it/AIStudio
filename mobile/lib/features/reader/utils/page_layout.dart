import 'package:flutter/material.dart';
import 'package:manhwamaniacs/features/settings/models/reader_defaults.dart';

/// Widest a page is drawn at 1x zoom, so a phone-shaped strip is not stretched
/// across a tablet.
const double maxContentWidth = 768;

/// Ratio a page is laid out at until its real size is known. Chosen to look
/// like a print page rather than a webtoon strip, because guessing tall would
/// leave a screenful of empty backdrop under every short page.
const double defaultAspectRatio = 2 / 3;

BoxFit readerFitModeToBoxFit(ReaderFitMode mode) => switch (mode) {
      ReaderFitMode.width => BoxFit.fitWidth,
      ReaderFitMode.height => BoxFit.fitHeight,
      ReaderFitMode.screen => BoxFit.contain,
    };

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
