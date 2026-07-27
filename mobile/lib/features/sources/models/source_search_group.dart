import 'package:manhwamaniacs/features/library/models/global_search_result.dart';

/// Per-source view of `GET /sources/search`.
///
/// The endpoint returns the same hits twice: a flat `items` list (legacy, kept
/// for older builds) and `groups`, one entry per queried source plus the local
/// library. The app renders `groups` — Mihon-style, a section per source — so
/// the flat list is deliberately ignored here.
///
/// Ordering is decided server-side and must be preserved verbatim: `groups[0]`
/// is always the local library, then source groups best-relevance-first with
/// empty/error groups sinking to the bottom. Items inside a group are already
/// best-match-first.
enum SourceGroupStatus {
  ok,
  empty,
  error;

  static SourceGroupStatus parse(String? raw) => switch (raw) {
        'ok' => SourceGroupStatus.ok,
        'error' => SourceGroupStatus.error,
        _ => SourceGroupStatus.empty,
      };
}

class SourceSearchGroup {
  const SourceSearchGroup({
    required this.source,
    required this.sourceName,
    required this.status,
    this.iconUrl,
    this.error,
    this.total = 0,
    this.hasMore = false,
    this.items = const [],
  });

  /// Connector id, or null — which is what *identifies* the local-library
  /// group; there is no sentinel string for it.
  final String? source;
  final String sourceName;
  final String? iconUrl;
  final SourceGroupStatus status;

  /// Always set when [status] is `error`. Also set on an `empty` group whose
  /// results the backend discarded as irrelevant to the query, which is worth
  /// surfacing — "nothing matched" reads very differently from "the source
  /// answered with noise".
  final String? error;
  final int total;
  final bool hasMore;
  final List<GlobalSearchItem> items;

  bool get isLocal => source == null;
  bool get hasError => status == SourceGroupStatus.error;

  /// Stable identity for merging paginated responses and for keying widgets —
  /// the local group has no source id of its own.
  String get key => source ?? '@local';

  SourceSearchGroup copyWith({
    SourceGroupStatus? status,
    String? error,
    bool clearError = false,
    int? total,
    bool? hasMore,
    List<GlobalSearchItem>? items,
  }) =>
      SourceSearchGroup(
        source: source,
        sourceName: sourceName,
        iconUrl: iconUrl,
        status: status ?? this.status,
        error: clearError ? null : (error ?? this.error),
        total: total ?? this.total,
        hasMore: hasMore ?? this.hasMore,
        items: items ?? this.items,
      );

  factory SourceSearchGroup.fromJson(Map<String, dynamic> json) {
    final source = json['source'] as String?;
    final name = json['source_name'] as String?;
    final items = (json['items'] as List<dynamic>? ?? const [])
        .map((e) => GlobalSearchItem.fromJson(e as Map<String, dynamic>))
        .toList();
    return SourceSearchGroup(
      source: source,
      sourceName: (name == null || name.isEmpty) ? (source ?? 'Unknown') : name,
      iconUrl: json['icon_url'] as String?,
      status: SourceGroupStatus.parse(json['status'] as String?),
      error: json['error'] as String?,
      total: (json['total'] as num?)?.toInt() ?? items.length,
      hasMore: json['has_more'] as bool? ?? false,
      items: items,
    );
  }
}

class GroupedSearchResult {
  const GroupedSearchResult({
    this.groups = const [],
    this.sourcesQueried = 0,
    this.sourcesFailed = 0,
    this.page = 1,
    this.hasMore = false,
    this.isLoadingMore = false,
  });

  final List<SourceSearchGroup> groups;
  final int sourcesQueried;
  final int sourcesFailed;
  final int page;
  final bool hasMore;

  /// UI-only flag toggled while a `loadMore` page request is in flight.
  final bool isLoadingMore;

  int get resultCount =>
      groups.fold(0, (count, group) => count + group.items.length);

  bool get isEmpty => resultCount == 0;

  /// Groups that actually have something to render, in server order.
  List<SourceSearchGroup> get groupsWithResults =>
      [for (final group in groups) if (group.items.isNotEmpty) group];

  GroupedSearchResult copyWith({
    List<SourceSearchGroup>? groups,
    int? sourcesQueried,
    int? sourcesFailed,
    int? page,
    bool? hasMore,
    bool? isLoadingMore,
  }) =>
      GroupedSearchResult(
        groups: groups ?? this.groups,
        sourcesQueried: sourcesQueried ?? this.sourcesQueried,
        sourcesFailed: sourcesFailed ?? this.sourcesFailed,
        page: page ?? this.page,
        hasMore: hasMore ?? this.hasMore,
        isLoadingMore: isLoadingMore ?? this.isLoadingMore,
      );

  /// Fold a later page into this one.
  ///
  /// Groups are matched by [SourceSearchGroup.key] and their items appended, so
  /// page 2 extends each section in place instead of pushing a second copy of
  /// every source onto the screen. The page-1 group order is kept — re-sorting
  /// mid-scroll would make sections jump under the user's finger — and any
  /// source that only shows up on a later page is appended at the end.
  GroupedSearchResult mergePage(GroupedSearchResult next) {
    final incoming = {for (final group in next.groups) group.key: group};
    final merged = <SourceSearchGroup>[];

    for (final group in groups) {
      final addition = incoming.remove(group.key);
      if (addition == null) {
        merged.add(group);
        continue;
      }
      final items = [...group.items, ...addition.items];
      merged.add(
        group.copyWith(
          // A source that failed on page 1 but answered on page 2 (or the
          // reverse) reports its newest state, not its first one.
          status: addition.status,
          error: addition.error,
          clearError: addition.error == null,
          total: items.length,
          hasMore: addition.hasMore,
          items: items,
        ),
      );
    }
    merged.addAll(incoming.values);

    return GroupedSearchResult(
      groups: merged,
      sourcesQueried: next.sourcesQueried,
      sourcesFailed: next.sourcesFailed,
      page: next.page,
      hasMore: next.hasMore,
    );
  }

  factory GroupedSearchResult.fromJson(Map<String, dynamic> json) =>
      GroupedSearchResult(
        groups: (json['groups'] as List<dynamic>? ?? const [])
            .map((e) => SourceSearchGroup.fromJson(e as Map<String, dynamic>))
            .toList(),
        sourcesQueried: (json['sources_queried'] as num?)?.toInt() ?? 0,
        sourcesFailed: (json['sources_failed'] as num?)?.toInt() ?? 0,
        page: (json['page'] as num?)?.toInt() ?? 1,
        hasMore: json['has_more'] as bool? ?? false,
      );
}
