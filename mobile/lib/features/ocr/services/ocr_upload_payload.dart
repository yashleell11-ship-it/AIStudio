import 'package:manhwamaniacs/features/ocr/models/page_text.dart';

/// The ingest bounds `backend/routes/ocr.py` enforces, mirrored here.
///
/// They are mirrored rather than discovered because of what a breach costs:
/// the backend rejects an over-limit upload with a single 422 for the *whole*
/// request, which would throw away every minute the phone just spent running
/// Vision/ML Kit over a 60-page chapter. Trimming client-side turns "lose the
/// chapter" into "lose the geometry on a freakishly wordy chapter", so these
/// constants must stay in step with the backend's.
const int kOcrMaxPages = 500;
const int kOcrMaxPageTextChars = 20000;
const int kOcrMaxBoxesPerPage = 300;
const int kOcrMaxBoxTextChars = 1000;
const int kOcrMaxTotalTextChars = 2000000;

/// Trims [pages] until it satisfies every bound above, in the order that
/// sheds the least useful information first:
///
/// 1. **Per-item caps** — page text, box text, and box count are truncated in
///    place. A page over 20 000 characters is not a real chapter of dialogue;
///    it is a page of dense scanned prose, and its first 20 000 characters
///    are what search would ever match on anyway.
/// 2. **Boxes before text**, if the total is still over budget. Boxes exist
///    for future in-reader highlighting; the page text is what `/ocr/search`
///    actually indexes. Dropping every box is roughly halving the payload
///    while losing nothing searchable.
/// 3. **An even per-page text budget**, only if boxless text alone still
///    exceeds the total. Spreading the shortfall evenly keeps every page
///    represented rather than uploading the first N pages in full and
///    nothing at all for the rest.
///
/// Pages beyond [kOcrMaxPages] are dropped last-first. A chapter that long
/// does not exist in practice — the alternative (splitting across requests)
/// would be worse than useless, since the backend upsert *replaces* a
/// chapter's transcript, so a second request would erase the first.
List<PageText> capOcrPagesForUpload(List<PageText> pages) {
  var capped = [
    for (final page in pages.take(kOcrMaxPages))
      page.copyWith(
        text: _truncate(page.text, kOcrMaxPageTextChars),
        boxes: [
          for (final box in page.boxes.take(kOcrMaxBoxesPerPage))
            box.text.length <= kOcrMaxBoxTextChars
                ? box
                : box.copyWithText(_truncate(box.text, kOcrMaxBoxTextChars)),
        ],
      ),
  ];

  if (ocrPayloadTextLength(capped) <= kOcrMaxTotalTextChars) return capped;

  capped = [for (final page in capped) page.copyWith(boxes: const [])];
  if (ocrPayloadTextLength(capped) <= kOcrMaxTotalTextChars) return capped;

  final perPageBudget = kOcrMaxTotalTextChars ~/ capped.length;
  return [
    for (final page in capped)
      page.copyWith(text: _truncate(page.text, perPageBudget)),
  ];
}

/// The figure the backend's `_cap_total_text` validator computes: page text
/// plus every box's text, across the whole payload.
int ocrPayloadTextLength(List<PageText> pages) {
  var total = 0;
  for (final page in pages) {
    total += page.text.length;
    for (final box in page.boxes) {
      total += box.text.length;
    }
  }
  return total;
}

String _truncate(String value, int maxChars) =>
    value.length <= maxChars ? value : value.substring(0, maxChars);
