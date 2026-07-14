class SourceSummary {
  const SourceSummary({
    required this.id,
    required this.name,
    required this.description,
    required this.browsable,
    required this.supportsImport,
    this.iconUrl,
  });

  final String id;
  final String name;
  final String description;
  final bool browsable;
  final bool supportsImport;
  final String? iconUrl;

  factory SourceSummary.fromJson(Map<String, dynamic> json) => SourceSummary(
        id: json['id'] as String,
        name: json['name'] as String,
        description: json['description'] as String,
        browsable: json['browsable'] as bool,
        supportsImport: json['supports_import'] as bool,
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
