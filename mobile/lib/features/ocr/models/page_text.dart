/// One recognized text region on a page.
///
/// Geometry is **normalized 0..1 with a top-left origin**, which is a
/// deliberate choice rather than either platform's native convention: Vision
/// hands back normalized rects with a *bottom-left* origin, ML Kit hands back
/// pixel rects with a top-left origin. Both native handlers convert to this
/// one shape, so a box uploaded from an iPhone and a box uploaded from an
/// Android phone mean the same thing to anything that later draws them over
/// a page image at an arbitrary display size.
///
/// `left`/`top`/`right`/`bottom` — which the backend also accepts — are
/// deliberately not sent: they are `x`/`y`/`x+width`/`y+height` and nothing
/// more, and the ingest service stores whatever arrives verbatim, so
/// duplicating them would only inflate the row.
class OcrTextBox {
  const OcrTextBox({
    required this.text,
    this.x,
    this.y,
    this.width,
    this.height,
    this.confidence,
  });

  final String text;
  final double? x;
  final double? y;
  final double? width;
  final double? height;

  /// 0..1 where the engine reports one. ML Kit exposes no per-block
  /// confidence, so Android uploads leave this `null` — hence nullable
  /// rather than a fabricated 1.0.
  final double? confidence;

  /// Parses one box from the `mm/ocr` channel. Every field but `text` is
  /// optional and any non-numeric value is dropped rather than throwing —
  /// a malformed box must degrade to "text without geometry", never fail
  /// the whole chapter's run.
  factory OcrTextBox.fromChannel(Map<Object?, Object?> raw) => OcrTextBox(
        text: raw['text'] is String ? raw['text']! as String : '',
        x: _asDouble(raw['x']),
        y: _asDouble(raw['y']),
        width: _asDouble(raw['width']),
        height: _asDouble(raw['height']),
        confidence: _asDouble(raw['confidence']),
      );

  Map<String, dynamic> toJson() => {
        'text': text,
        if (x != null) 'x': x,
        if (y != null) 'y': y,
        if (width != null) 'width': width,
        if (height != null) 'height': height,
        if (confidence != null) 'confidence': confidence,
      };

  OcrTextBox copyWithText(String newText) => OcrTextBox(
        text: newText,
        x: x,
        y: y,
        width: width,
        height: height,
        confidence: confidence,
      );

  static double? _asDouble(Object? value) =>
      value is num ? value.toDouble() : null;
}

/// The OCR result for a single page — the unit `OcrEngine.recognize` returns
/// and the unit `POST /ocr/chapter` uploads.
///
/// [page] is the chapter's real 1-based page number, not the index within a
/// recognize() batch: the run controller drives the engine one page at a time
/// off `DownloadsStore.localPagePaths`, whose keys are the real numbers, and
/// stamps them here so a chapter with a gap (a blob deleted by hand through
/// the Files app) still uploads correctly numbered text.
class PageText {
  const PageText({
    required this.page,
    required this.text,
    this.boxes = const [],
  });

  final int page;
  final String text;
  final List<OcrTextBox> boxes;

  bool get isEmpty => text.trim().isEmpty;

  /// Parses one page from the `mm/ocr` channel, stamping [page] from the
  /// caller (the native side is handed paths, not page numbers).
  factory PageText.fromChannel(Map<Object?, Object?> raw, {required int page}) {
    final rawBoxes = raw['boxes'];
    return PageText(
      page: page,
      text: raw['text'] is String ? raw['text']! as String : '',
      boxes: rawBoxes is List
          ? [
              for (final box in rawBoxes)
                if (box is Map<Object?, Object?>) OcrTextBox.fromChannel(box),
            ]
          : const [],
    );
  }

  PageText copyWith({String? text, List<OcrTextBox>? boxes}) => PageText(
        page: page,
        text: text ?? this.text,
        boxes: boxes ?? this.boxes,
      );

  Map<String, dynamic> toJson() => {
        'page': page,
        'text': text,
        if (boxes.isNotEmpty) 'boxes': [for (final box in boxes) box.toJson()],
      };
}
