class ChapterSummary {
  const ChapterSummary({
    this.id,
    required this.seriesId,
    required this.title,
    this.number,
    required this.pageCount,
    this.folderPath,
    this.archivePath,
    this.localChapterId,
    this.isDownloaded = true,
    this.isRead = false,
    this.sourceChapterId,
  });

  /// Local chapter id. Null for remote-only chapters that exist in the source
  /// catalog but have not been downloaded.
  final int? id;
  final int seriesId;
  final String title;
  final double? number;
  final int pageCount;
  final String? folderPath;
  final String? archivePath;

  /// Same as [id] when a local copy exists; null otherwise.
  final int? localChapterId;

  /// Whether a local (downloaded) copy of this chapter exists.
  final bool isDownloaded;

  /// Whether the chapter has been marked read.
  final bool isRead;

  /// Source chapter id (e.g. 'killer-pietro-a80d257e:2'). Null when unknown.
  final String? sourceChapterId;

  factory ChapterSummary.fromJson(Map<String, dynamic> json) => ChapterSummary(
        id: json['id'] as int?,
        seriesId: json['series_id'] as int,
        title: json['title'] as String,
        number: json['number'] != null ? (json['number'] as num).toDouble() : null,
        pageCount: (json['page_count'] as int?) ?? 0,
        folderPath: json['folder_path'] as String?,
        archivePath: json['archive_path'] as String?,
        localChapterId: json['local_chapter_id'] as int?,
        isDownloaded: (json['is_downloaded'] as bool?) ?? (json['id'] != null),
        isRead: (json['is_read'] as bool?) ?? false,
        sourceChapterId: json['source_chapter_id'] as String?,
      );
}

class PageInfo {
  const PageInfo({
    required this.id,
    required this.chapterId,
    required this.number,
    required this.filePath,
    this.width,
    this.height,
  });

  final int id;
  final int chapterId;
  final int number;
  final String filePath;
  final int? width;
  final int? height;

  factory PageInfo.fromJson(Map<String, dynamic> json) => PageInfo(
        id: json['id'] as int,
        chapterId: json['chapter_id'] as int,
        number: json['number'] as int,
        filePath: json['file_path'] as String,
        width: json['width'] as int?,
        height: json['height'] as int?,
      );
}

class ChapterDetail {
  const ChapterDetail({
    required this.id,
    required this.seriesId,
    required this.title,
    this.number,
    required this.pageCount,
    required this.pages,
  });

  final int id;
  final int seriesId;
  final String title;
  final double? number;
  final int pageCount;
  final List<PageInfo> pages;

  factory ChapterDetail.fromJson(Map<String, dynamic> json) => ChapterDetail(
        id: json['id'] as int,
        seriesId: json['series_id'] as int,
        title: json['title'] as String,
        number: json['number'] != null ? (json['number'] as num).toDouble() : null,
        pageCount: json['page_count'] as int,
        pages: (json['pages'] as List<dynamic>)
            .map((e) => PageInfo.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}
