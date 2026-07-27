class SourceSummary {
  const SourceSummary({
    required this.id,
    required this.name,
    required this.description,
    required this.browsable,
    required this.supportsImport,
    this.mature = false,
    this.iconUrl,
  });

  final String id;
  final String name;
  final String description;
  final bool browsable;
  final bool supportsImport;

  /// Adult connector. The backend only lists these at all when the profile's
  /// mature gate is open, so this is a badge/filter hint, not an access check.
  final bool mature;
  final String? iconUrl;

  factory SourceSummary.fromJson(Map<String, dynamic> json) => SourceSummary(
        id: json['id'] as String,
        name: json['name'] as String,
        description: json['description'] as String,
        browsable: json['browsable'] as bool,
        supportsImport: json['supports_import'] as bool,
        mature: json['mature'] as bool? ?? false,
        iconUrl: json['icon_url'] as String?,
      );
}

class SourceBrowseMode {
  const SourceBrowseMode({required this.id, required this.label});

  final String id;
  final String label;

  factory SourceBrowseMode.fromJson(Map<String, dynamic> json) => SourceBrowseMode(
        id: json['id'] as String,
        label: json['label'] as String,
      );
}
