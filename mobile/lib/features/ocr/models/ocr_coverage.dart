/// `GET /ocr/coverage` — which chapters of one series already have a stored
/// transcript, so the client only offers to OCR the gaps.
///
/// A `word_count` of 0 counts as *not* covered: the ingest service refuses to
/// overwrite a good transcript with an empty one, so an empty row is a
/// chapter someone's engine failed on, not one that is done.
class OcrCoverage {
  const OcrCoverage({
    required this.sourceId,
    required this.seriesKey,
    required this.wordCountByChapterKey,
  });

  final String sourceId;
  final String seriesKey;
  final Map<String, int> wordCountByChapterKey;

  static const OcrCoverage empty = OcrCoverage(
    sourceId: '',
    seriesKey: '',
    wordCountByChapterKey: {},
  );

  bool covers(String chapterKey) =>
      (wordCountByChapterKey[chapterKey] ?? 0) > 0;

  int get coveredChapterCount =>
      wordCountByChapterKey.values.where((wc) => wc > 0).length;

  factory OcrCoverage.fromJson(Map<String, dynamic> json) {
    final chapters = json['chapters'];
    return OcrCoverage(
      sourceId: json['source_id'] as String? ?? '',
      seriesKey: json['series_key'] as String? ?? '',
      wordCountByChapterKey: {
        if (chapters is List)
          for (final entry in chapters)
            if (entry is Map<String, dynamic> && entry['chapter_key'] is String)
              entry['chapter_key']! as String:
                  (entry['word_count'] as num?)?.toInt() ?? 0,
      },
    );
  }
}
