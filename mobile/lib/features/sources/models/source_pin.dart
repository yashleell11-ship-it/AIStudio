/// A pinned source as returned by `GET/PUT /sources/pins`.
///
/// Pins live on the server and are scoped to `(user_id, profile_id)`, so they
/// follow the account across devices and never leak between accounts or between
/// profiles of one account. [sourceId] is a connector key, not a foreign key —
/// a connector can be excluded, renamed or hidden by the mature gate, in which
/// case the pin is still returned with [available] `false` rather than silently
/// disappearing from the user's ordering.
class SourcePin {
  const SourcePin({
    required this.sourceId,
    required this.sortOrder,
    required this.name,
    this.iconUrl,
    this.mature = false,
    this.available = true,
  });

  final String sourceId;

  /// 0-based, dense, and identical to the position in the pins array.
  final int sortOrder;

  /// Connector display name; falls back to [sourceId] when unresolvable.
  final String name;
  final String? iconUrl;
  final bool mature;

  /// False when [sourceId] no longer resolves to a connector this profile can
  /// see. Such a pin is shown greyed out instead of vanishing.
  final bool available;

  factory SourcePin.fromJson(Map<String, dynamic> json) {
    final id = '${json['source_id']}';
    final name = json['name'] as String?;
    return SourcePin(
      sourceId: id,
      sortOrder: (json['sort_order'] as num?)?.toInt() ?? 0,
      name: (name == null || name.isEmpty) ? id : name,
      iconUrl: json['icon_url'] as String?,
      mature: json['mature'] as bool? ?? false,
      available: json['available'] as bool? ?? true,
    );
  }

  /// Only used for the offline write-through cache, which round-trips through
  /// [SourcePin.fromJson] — so the keys must match the API payload exactly.
  Map<String, dynamic> toJson() => {
        'source_id': sourceId,
        'sort_order': sortOrder,
        'name': name,
        'icon_url': iconUrl,
        'mature': mature,
        'available': available,
      };
}
