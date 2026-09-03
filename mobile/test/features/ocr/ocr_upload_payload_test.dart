import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/ocr/models/page_text.dart';
import 'package:manhwamaniacs/features/ocr/services/ocr_upload_payload.dart';

/// The backend rejects an over-limit upload with a single 422 for the whole
/// request, which would throw away a full chapter's OCR run. These tests pin
/// the client-side trimming that makes that unreachable — every bound in
/// `backend/routes/ocr.py`, and the order the trimming sheds information in.

PageText _page(int number, String text, {List<OcrTextBox> boxes = const []}) =>
    PageText(page: number, text: text, boxes: boxes);

OcrTextBox _box(String text) => OcrTextBox(text: text);

void main() {
  group('per-item bounds', () {
    test('truncates page text at the per-page ceiling', () {
      final capped = capOcrPagesForUpload([
        _page(1, 'x' * (kOcrMaxPageTextChars + 500)),
      ]);

      expect(capped.single.text.length, kOcrMaxPageTextChars);
    });

    test('drops boxes beyond the per-page ceiling, keeping reading order', () {
      final capped = capOcrPagesForUpload([
        _page(
          1,
          'hello',
          boxes: [
            for (var i = 0; i < kOcrMaxBoxesPerPage + 10; i++) _box('box-$i'),
          ],
        ),
      ]);

      expect(capped.single.boxes, hasLength(kOcrMaxBoxesPerPage));
      expect(capped.single.boxes.first.text, 'box-0');
    });

    test('truncates an over-long box, keeping its geometry', () {
      final capped = capOcrPagesForUpload([
        _page(
          1,
          'hello',
          boxes: [
            OcrTextBox(
              text: 'y' * (kOcrMaxBoxTextChars + 1),
              x: 0.25,
              y: 0.5,
              width: 0.1,
              height: 0.2,
              confidence: 0.9,
            ),
          ],
        ),
      ]);

      final box = capped.single.boxes.single;
      expect(box.text.length, kOcrMaxBoxTextChars);
      expect(box.x, 0.25);
      expect(box.confidence, 0.9);
    });

    test('drops pages past the page ceiling', () {
      final capped = capOcrPagesForUpload([
        for (var i = 1; i <= kOcrMaxPages + 3; i++) _page(i, 'page $i'),
      ]);

      expect(capped, hasLength(kOcrMaxPages));
      expect(capped.last.page, kOcrMaxPages);
    });
  });

  group('total-text bound', () {
    test('leaves a payload under budget completely untouched', () {
      final pages = [
        _page(1, 'chapter one', boxes: [_box('chapter'), _box('one')]),
        _page(2, 'chapter two'),
      ];

      final capped = capOcrPagesForUpload(pages);

      expect(capped[0].text, 'chapter one');
      expect(capped[0].boxes, hasLength(2));
      expect(capped[1].text, 'chapter two');
    });

    test('sheds boxes before text when the total is over budget', () {
      // 200 pages x (10k text + 10k of boxes) = 4M chars; text alone is 2M,
      // which is exactly the ceiling, so dropping boxes is enough.
      final pages = [
        for (var i = 1; i <= 200; i++)
          _page(
            i,
            'a' * 10000,
            boxes: [for (var b = 0; b < 10; b++) _box('b' * 1000)],
          ),
      ];

      final capped = capOcrPagesForUpload(pages);

      expect(ocrPayloadTextLength(capped), lessThanOrEqualTo(kOcrMaxTotalTextChars));
      expect(capped.every((p) => p.boxes.isEmpty), isTrue);
      // Text survived in full — the whole point of dropping boxes first.
      expect(capped.every((p) => p.text.length == 10000), isTrue);
    });

    test('spreads the shortfall evenly rather than dropping late pages', () {
      // 300 pages of full-length text = 6M chars of text alone.
      final pages = [
        for (var i = 1; i <= 300; i++) _page(i, 'a' * kOcrMaxPageTextChars),
      ];

      final capped = capOcrPagesForUpload(pages);

      expect(capped, hasLength(300));
      expect(ocrPayloadTextLength(capped), lessThanOrEqualTo(kOcrMaxTotalTextChars));
      // Every page still carries text — a late page is not silently emptied.
      expect(capped.every((p) => p.text.isNotEmpty), isTrue);
      expect(capped.first.text.length, capped.last.text.length);
    });
  });

  test('ocrPayloadTextLength counts page text plus every box, like the server',
      () {
    final total = ocrPayloadTextLength([
      _page(1, 'abcde', boxes: [_box('xy'), _box('z')]),
      _page(2, 'fg'),
    ]);

    expect(total, 5 + 2 + 1 + 2);
  });

  group('wire shape', () {
    test('omits an empty boxes list rather than sending null geometry', () {
      final json = _page(3, 'text only').toJson();

      expect(json, {'page': 3, 'text': 'text only'});
    });

    test('omits geometry fields the engine did not report', () {
      final json = OcrTextBox(text: 'hi', x: 0.1).toJson();

      expect(json, {'text': 'hi', 'x': 0.1});
    });
  });
}
