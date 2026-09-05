import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/reader/utils/reader_decode_diagnostics.dart';

String? _report({
  int? declaredWidth,
  int? declaredHeight,
  int? requestedWidth,
  required int decodedWidth,
  required int decodedHeight,
}) =>
    readerDecodeReport(
      label: 'Chapter 1 page 3',
      declaredWidth: declaredWidth,
      declaredHeight: declaredHeight,
      requestedWidth: requestedWidth,
      decodedWidth: decodedWidth,
      decodedHeight: decodedHeight,
    );

void main() {
  group('readerExpectedDecodedHeight', () {
    test('scales the declared height by the width actually asked for', () {
      expect(
        readerExpectedDecodedHeight(
          declaredWidth: 1440,
          declaredHeight: 10000,
          requestedWidth: 720,
        ),
        5000,
      );
    });

    test('a request wider than the source is a no-op (no upscaling)', () {
      expect(
        readerExpectedDecodedHeight(
          declaredWidth: 720,
          declaredHeight: 14668,
          requestedWidth: 2304,
        ),
        14668,
      );
    });

    test('says nothing when the source declared nothing', () {
      expect(
        readerExpectedDecodedHeight(
          declaredWidth: null,
          declaredHeight: null,
          requestedWidth: 1080,
        ),
        isNull,
      );
    });
  });

  group('readerDecodeReport', () {
    test('stays quiet when the page decoded exactly as asked', () {
      expect(
        _report(
          declaredWidth: 720,
          declaredHeight: 14668,
          requestedWidth: 1080,
          decodedWidth: 720,
          decodedHeight: 14668,
        ),
        isNull,
      );
    });

    test('stays quiet about a page whose size nothing declared', () {
      expect(
        _report(requestedWidth: 1080, decodedWidth: 720, decodedHeight: 9600),
        isNull,
      );
    });

    test('names the texture clamp and how far the page is squashed', () {
      final report = _report(
        declaredWidth: 720,
        declaredHeight: 14668,
        requestedWidth: 2304,
        decodedWidth: 720,
        decodedHeight: 8192,
      );

      expect(report, isNotNull);
      expect(report, contains('source 720x14668'));
      expect(report, contains('got 720x8192'));
      expect(report, contains('GPU max texture size'));
      expect(report, contains('SQUASHED'));
      // 14668 / 8192.
      expect(report, contains('1.79x too short'));
    });

    test('flags a clamp-shaped height even with no declared size to compare', () {
      final report =
          _report(requestedWidth: 1080, decodedWidth: 1080, decodedHeight: 4096);

      expect(report, contains('source size not declared'));
      expect(report, contains('GPU max texture size'));
      // Nothing to compare against, so the report says so rather than
      // asserting a squash factor it cannot know.
      expect(report, contains('unless this page really is 4096 px tall'));
      expect(report, isNot(contains('too short')));
    });

    test('reports a plain mismatch without blaming the clamp', () {
      final report = _report(
        declaredWidth: 800,
        declaredHeight: 12000,
        requestedWidth: 1080,
        decodedWidth: 800,
        decodedHeight: 6000,
      );

      expect(report, contains('expected height 12000'));
      expect(report, isNot(contains('GPU max texture size')));
    });

    test('tolerates the decoder rounding a scaled height by a pixel', () {
      expect(
        _report(
          declaredWidth: 1440,
          declaredHeight: 9999,
          requestedWidth: 1080,
          decodedWidth: 1080,
          decodedHeight: 7500, // exact would be 7499.25 -> 7499
        ),
        isNull,
      );
    });
  });
}
