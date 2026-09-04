import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/library/models/followed_series.dart';

class LibraryListState {
  const LibraryListState({
    this.items = const [],
    this.total = 0,
    this.page = 1,
    this.hasNext = false,
    this.isLoadingMore = false,
    this.isOffline = false,
    this.error,
  });

  final List<FollowedSeries> items;
  final int total;
  final int page;
  final bool hasNext;
  final bool isLoadingMore;

  /// This list came from the offline cache because the server could not be
  /// reached — the last library this profile synced, not a live answer. The
  /// screen must say so: silently serving a stale shelf as a live one is how
  /// a user ends up believing a series they followed on another device has
  /// vanished.
  final bool isOffline;
  final AppError? error;

  bool get isEmpty => items.isEmpty;

  LibraryListState copyWith({
    List<FollowedSeries>? items,
    int? total,
    int? page,
    bool? hasNext,
    bool? isLoadingMore,
    bool? isOffline,
    AppError? error,
    bool clearError = false,
  }) {
    return LibraryListState(
      items: items ?? this.items,
      total: total ?? this.total,
      page: page ?? this.page,
      hasNext: hasNext ?? this.hasNext,
      isLoadingMore: isLoadingMore ?? this.isLoadingMore,
      isOffline: isOffline ?? this.isOffline,
      error: clearError ? null : (error ?? this.error),
    );
  }
}
