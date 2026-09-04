/// The two values `content_kind` takes on the wire (`connectors/registry.py`).
const String kMangaContentKind = 'manga';
const String kNovelContentKind = 'novel';

class SourceSummary {
  const SourceSummary({
    required this.id,
    required this.name,
    required this.description,
    required this.browsable,
    required this.supportsImport,
    this.mature = false,
    this.iconUrl,
    this.contentKind = kMangaContentKind,
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

  /// What this connector serves: `"manga"` (pages) or `"novel"` (prose).
  ///
  /// Read tolerantly and defaulted to manga: a connector that omits the field
  /// — every one of them, before novels existed — must keep behaving exactly
  /// as it does today. Nothing is ever *labelled* a novel by accident, which
  /// is what makes "not a novel" a safe definition of manga.
  final String contentKind;

  factory SourceSummary.fromJson(Map<String, dynamic> json) => SourceSummary(
        id: json['id'] as String,
        name: json['name'] as String,
        description: json['description'] as String,
        browsable: json['browsable'] as bool,
        supportsImport: json['supports_import'] as bool,
        mature: json['mature'] as bool? ?? false,
        iconUrl: json['icon_url'] as String?,
        contentKind: json['content_kind'] is String
            ? json['content_kind']! as String
            : kMangaContentKind,
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
