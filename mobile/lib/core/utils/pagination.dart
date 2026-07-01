/// Parameters for paginated API requests.
class PaginationParams {
  const PaginationParams({this.page = 1, this.perPage = 20});

  final int page;
  final int perPage;

  PaginationParams nextPage() => PaginationParams(page: page + 1, perPage: perPage);

  Map<String, dynamic> toQueryParams() => {
        'page': page,
        'per_page': perPage,
      };
}

/// Typed paginated response, matching the backend `{ items, total, page, per_page, has_next }` shape.
class PagedResult<T> {
  const PagedResult({
    required this.items,
    required this.total,
    required this.page,
    required this.perPage,
    required this.hasNext,
  });

  final List<T> items;
  final int total;
  final int page;
  final int perPage;
  final bool hasNext;

  bool get isFirstPage => page == 1;
  int get totalPages => perPage > 0 ? (total / perPage).ceil() : 0;

  PagedResult<T> appendItems(List<T> newItems, {required bool hasNext}) {
    return PagedResult<T>(
      items: [...items, ...newItems],
      total: total,
      page: page,
      perPage: perPage,
      hasNext: hasNext,
    );
  }

  PagedResult<R> mapItems<R>(R Function(T item) f) {
    return PagedResult<R>(
      items: items.map(f).toList(),
      total: total,
      page: page,
      perPage: perPage,
      hasNext: hasNext,
    );
  }

  factory PagedResult.fromJson(
    Map<String, dynamic> json,
    T Function(Map<String, dynamic>) fromJsonItem,
  ) {
    return PagedResult<T>(
      items: (json['items'] as List<dynamic>)
          .map((e) => fromJsonItem(e as Map<String, dynamic>))
          .toList(),
      total: json['total'] as int,
      page: json['page'] as int,
      perPage: json['per_page'] as int,
      hasNext: json['has_next'] as bool,
    );
  }
}
