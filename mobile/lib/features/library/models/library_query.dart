enum LibraryFilter { all, downloaded, reading, completed }

enum LibrarySort {
  updated,
  dateAdded,
  title,
  recent,
  author,
  year,
  totalChapters,
}

enum LibraryViewMode { grid, list }

enum LibraryEmptyState { library, search, filter }

/// Sort options exposed on the library browse screen.
const libraryBrowseSortOptions = [
  LibrarySort.recent,
  LibrarySort.dateAdded,
  LibrarySort.title,
];

/// Filter chips exposed on the library browse screen.
const libraryBrowseFilterOptions = [
  LibraryFilter.all,
  LibraryFilter.downloaded,
  LibraryFilter.reading,
  LibraryFilter.completed,
];

class LibraryQuery {
  const LibraryQuery({
    this.search = '',
    this.sort = LibrarySort.recent,
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

  String? get readingStatusParam {
    if (isSearching) return null;
    return switch (filter) {
      LibraryFilter.all || LibraryFilter.downloaded => null,
      LibraryFilter.reading => 'reading',
      LibraryFilter.completed => 'completed',
    };
  }

  String get sortParam => switch (sort) {
        LibrarySort.updated => 'updated',
        LibrarySort.dateAdded => 'date_added',
        LibrarySort.title => 'title',
        LibrarySort.recent => 'recent',
        LibrarySort.author => 'author',
        LibrarySort.year => 'year',
        LibrarySort.totalChapters => 'total_chapters',
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
        LibrarySort.updated => 'Recently Updated',
        LibrarySort.dateAdded => 'Recently Added',
        LibrarySort.title => 'Alphabetical',
        LibrarySort.recent => 'Recently Read',
        LibrarySort.author => 'Author',
        LibrarySort.year => 'Year',
        LibrarySort.totalChapters => 'Total Chapters',
      };
}

extension LibraryFilterLabel on LibraryFilter {
  String get label => switch (this) {
        LibraryFilter.all => 'All',
        LibraryFilter.downloaded => 'Downloaded',
        LibraryFilter.reading => 'Reading',
        LibraryFilter.completed => 'Completed',
      };
}
