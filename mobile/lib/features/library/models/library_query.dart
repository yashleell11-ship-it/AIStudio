enum LibraryFilter { all, reading, completed }

/// Values `GET /library/series` understands via its `sort` query param
/// (`FollowedSeriesService.list_series`). A leading `-` reverses; unused here
/// since the toolbar only exposes forward orderings.
enum LibrarySort { recentlyUpdated, recentlyAdded, title }

enum LibraryViewMode { grid, list }

enum LibraryEmptyState { library, search, filter }

/// Sort options exposed on the library browse screen.
const libraryBrowseSortOptions = [
  LibrarySort.recentlyUpdated,
  LibrarySort.recentlyAdded,
  LibrarySort.title,
];

/// Filter chips exposed on the library browse screen.
const libraryBrowseFilterOptions = [
  LibraryFilter.all,
  LibraryFilter.reading,
  LibraryFilter.completed,
];

class LibraryQuery {
  const LibraryQuery({
    this.search = '',
    this.sort = LibrarySort.recentlyUpdated,
    this.filter = LibraryFilter.all,
    this.favoritesOnly = false,
    this.viewMode = LibraryViewMode.grid,
  });

  final String search;
  final LibrarySort sort;
  final LibraryFilter filter;
  final bool favoritesOnly;
  final LibraryViewMode viewMode;

  bool get isSearching => search.trim().isNotEmpty;

  LibraryEmptyState get emptyState {
    if (isSearching) return LibraryEmptyState.search;
    if (favoritesOnly || filter != LibraryFilter.all) {
      return LibraryEmptyState.filter;
    }
    return LibraryEmptyState.library;
  }

  /// `GET /library/series` `reading_status` param — `null` clears the filter
  /// (search or the "all" chip).
  String? get readingStatusParam {
    return switch (filter) {
      LibraryFilter.all => null,
      LibraryFilter.reading => 'reading',
      LibraryFilter.completed => 'completed',
    };
  }

  String get sortParam => switch (sort) {
        LibrarySort.recentlyUpdated => 'recently_updated',
        LibrarySort.recentlyAdded => 'recently_added',
        LibrarySort.title => 'title',
      };

  LibraryQuery copyWith({
    String? search,
    LibrarySort? sort,
    LibraryFilter? filter,
    bool? favoritesOnly,
    LibraryViewMode? viewMode,
  }) {
    return LibraryQuery(
      search: search ?? this.search,
      sort: sort ?? this.sort,
      filter: filter ?? this.filter,
      favoritesOnly: favoritesOnly ?? this.favoritesOnly,
      viewMode: viewMode ?? this.viewMode,
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is LibraryQuery &&
          search == other.search &&
          sort == other.sort &&
          filter == other.filter &&
          favoritesOnly == other.favoritesOnly &&
          viewMode == other.viewMode;

  @override
  int get hashCode => Object.hash(search, sort, filter, favoritesOnly, viewMode);
}

extension LibrarySortLabel on LibrarySort {
  String get label => switch (this) {
        LibrarySort.recentlyUpdated => 'Recently Updated',
        LibrarySort.recentlyAdded => 'Recently Added',
        LibrarySort.title => 'Alphabetical',
      };
}

extension LibraryFilterLabel on LibraryFilter {
  String get label => switch (this) {
        LibraryFilter.all => 'All',
        LibraryFilter.reading => 'Reading',
        LibraryFilter.completed => 'Completed',
      };
}
