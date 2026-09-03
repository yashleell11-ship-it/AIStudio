import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/library/models/followed_series.dart';

class LibraryListState {
  const LibraryListState({
    this.items = const [],
    this.total = 0,
    this.page = 1,
    this.hasNext = false,
    this.isLoadingMore = false,
    this.error,
  });

  final List<FollowedSeries> items;
  final int total;
  final int page;
  final bool hasNext;
  final bool isLoadingMore;
  final AppError? error;

  bool get isEmpty => items.isEmpty;

  LibraryListState copyWith({
    List<FollowedSeries>? items,
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
