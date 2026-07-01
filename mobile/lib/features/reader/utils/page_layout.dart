import 'package:aistudio_mobile/features/library/models/chapter.dart';

const double defaultContainerWidth = 768;
const double maxContentWidth = 768;
const double defaultAspectRatio = 2 / 3;

double resolveContainerWidth(double measuredWidth) =>
    measuredWidth > 0 ? measuredWidth : defaultContainerWidth;

double estimatePageHeight(
  PageInfo page,
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

double pageAspectRatio(PageInfo page) {
  final width = page.width;
  final height = page.height;
  if (width != null && height != null && width > 0 && height > 0) {
    return width / height;
  }
  return defaultAspectRatio;
}

double estimateScrollOffsetToPage(
  List<PageInfo> pages,
  int pageNumber,
  double containerWidth,
  double zoom,
) {
  final targetIndex = (pageNumber - 1).clamp(0, pages.length - 1);
  var offset = 0.0;
  for (var index = 0; index < targetIndex; index++) {
    offset += estimatePageHeight(pages[index], containerWidth, zoom);
  }
  return offset;
}

int resolveVisiblePage(
  List<PageInfo> pages,
  double scrollOffset,
  double containerWidth,
  double zoom,
) {
  if (pages.isEmpty) return 1;

  var cumulative = 0.0;
  var activePage = 1;
  for (var index = 0; index < pages.length; index++) {
    final height = estimatePageHeight(pages[index], containerWidth, zoom);
    if (cumulative <= scrollOffset + 80) {
      activePage = index + 1;
    }
    cumulative += height;
  }
  return activePage;
}

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
