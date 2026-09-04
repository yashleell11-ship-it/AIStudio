import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/downloads/services/page_image_type.dart';

List<int> _isoBmff(String brand) => [
      0, 0, 0, 0x20, // box size
      ...ascii.encode('ftyp'),
      ...ascii.encode(brand),
      0, 0, 0, 0,
    ];

void main() {
  group('sniffPageImageType', () {
    test('recognises the formats sources actually serve', () {
      expect(sniffPageImageType(const [0xFF, 0xD8, 0xFF, 0xE0]),
          PageImageType.jpeg);
      expect(
        sniffPageImageType(const [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]),
        PageImageType.png,
      );
      expect(sniffPageImageType(ascii.encode('GIF89a')), PageImageType.gif);
      expect(sniffPageImageType(ascii.encode('BM......')), PageImageType.bmp);
    });

    test('reads WebP past the RIFF size field', () {
      final webp = [
        ...ascii.encode('RIFF'),
        0x24, 0x00, 0x00, 0x00, // size — deliberately not zero
        ...ascii.encode('WEBP'),
        ...ascii.encode('VP8 '),
      ];
      expect(sniffPageImageType(webp), PageImageType.webp);
    });

    test('separates AVIF from HEIC by ISO-BMFF brand', () {
      expect(sniffPageImageType(_isoBmff('avif')), PageImageType.avif);
      expect(sniffPageImageType(_isoBmff('heic')), PageImageType.heic);
      expect(sniffPageImageType(_isoBmff('mif1')), PageImageType.heic);
    });

    test('a RIFF container that is not WebP is not claimed as WebP', () {
      final wav = [
        ...ascii.encode('RIFF'),
        0, 0, 0, 0,
        ...ascii.encode('WAVE'),
      ];
      expect(sniffPageImageType(wav), PageImageType.unknown);
    });

    test('falls back to a neutral extension rather than guessing', () {
      expect(sniffPageImageType(const [1, 2, 3, 4]), PageImageType.unknown);
      expect(PageImageType.unknown.extension, '.img');
    });

    test('never reads past a truncated header', () {
      expect(sniffPageImageType(const []), PageImageType.unknown);
      expect(sniffPageImageType(const [0xFF, 0xD8]), PageImageType.unknown);
      // An ftyp box with no room for its brand must not be misread.
      expect(
        sniffPageImageType([0, 0, 0, 0x20, ...ascii.encode('ftyp'), 0x61]),
        PageImageType.unknown,
      );
    });
  });
}
