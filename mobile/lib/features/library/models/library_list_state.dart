import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/features/library/models/series_summary.dart';

class LibraryListState {
  const LibraryListState({
    this.items = const [],
    this.total = 0,
    this.page = 1,
    this.hasNext = false,
    this.isLoadingMore = false,
    this.error,
  });

  final List<SeriesSummary> items;
  final int total;
  final int page;
  final bool hasNext;
  final bool isLoadingMore;
  final AppError? error;

  bool get isEmpty => items.isEmpty;

  LibraryListState copyWith({
    List<SeriesSummary>? items,
    int? total,
    int? page,
    bool? hasNext,
    bool? isLoadingMore,
    AppError? error,
    bool clearError = false,
  }) {
    return LibraryListState(
      items: items ?? this.items,
      total: total ?? this.total,
      page: page ?? this.page,
      hasNext: hasNext ?? this.hasNext,
      isLoadingMore: isLoadingMore ?? this.isLoadingMore,
      error: clearError ? null : (error ?? this.error),
    );
  }
}
