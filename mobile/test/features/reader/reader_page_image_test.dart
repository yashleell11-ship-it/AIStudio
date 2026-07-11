import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/reader/widgets/reader_page_image.dart';
import 'package:manhwamaniacs/features/settings/models/reader_defaults.dart';

/// Builds an uncompressed PNG of [width] x [height] black pixels.
///
/// Written byte-by-byte (signature + IHDR + IDAT + IEND) so the test needs no
/// asset files and can shape images far taller than wide, matching AsuraScans
/// webtoon strips (e.g. 900x16000).
Uint8List buildPng(int width, int height) {
  final raw = BytesBuilder();
  for (var y = 0; y < height; y++) {
    raw.addByte(0); // filter: none
    for (var x = 0; x < width; x++) {
      raw.add(const [0, 0, 0, 255]);
    }
  }
  final idatData = _zlibStore(raw.takeBytes());

  final png = BytesBuilder();
  png.add(const [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]);
  final ihdr = BytesBuilder();
  ihdr
    ..add(_be32(width))
    ..add(_be32(height))
    ..addByte(8) // bit depth
    ..addByte(6) // color type RGBA
    ..addByte(0)
    ..addByte(0)
    ..addByte(0);
  png.add(_chunk('IHDR', ihdr.takeBytes()));
  png.add(_chunk('IDAT', idatData));
  png.add(_chunk('IEND', Uint8List(0)));
  return png.takeBytes();
}

Uint8List _be32(int value) => Uint8List(4)
  ..[0] = (value >> 24) & 0xFF
  ..[1] = (value >> 16) & 0xFF
  ..[2] = (value >> 8) & 0xFF
  ..[3] = value & 0xFF;

/// zlib stream with stored (uncompressed) deflate blocks.
Uint8List _zlibStore(Uint8List data) {
  final out = BytesBuilder();
  out.add(const [0x78, 0x01]);
  const blockSize = 65535;
  var offset = 0;
  while (true) {
    final remaining = data.length - offset;
    final len = remaining > blockSize ? blockSize : remaining;
    final isLast = offset + len >= data.length;
    out.addByte(isLast ? 1 : 0);
    out.addByte(len & 0xFF);
    out.addByte((len >> 8) & 0xFF);
    out.addByte(~len & 0xFF);
    out.addByte((~len >> 8) & 0xFF);
    out.add(data.sublist(offset, offset + len));
    offset += len;
    if (isLast) break;
  }
  out.add(_be32(_adler32(data)));
  return out.takeBytes();
}

int _adler32(Uint8List data) {
  var a = 1;
  var b = 0;
  for (final byte in data) {
    a = (a + byte) % 65521;
    b = (b + a) % 65521;
  }
  return (b << 16) | a;
}

Uint8List _chunk(String type, Uint8List data) {
  final out = BytesBuilder();
  out.add(_be32(data.length));
  final typeAndData = BytesBuilder()
    ..add(type.codeUnits)
    ..add(data);
  final body = typeAndData.takeBytes();
  out.add(body);
  out.add(_be32(_crc32(body)));
  return out.takeBytes();
}

int _crc32(Uint8List data) {
  var crc = 0xFFFFFFFF;
  for (final byte in data) {
    crc ^= byte;
    for (var bit = 0; bit < 8; bit++) {
      crc = (crc & 1) != 0 ? (crc >> 1) ^ 0xEDB88320 : crc >> 1;
    }
  }
  return crc ^ 0xFFFFFFFF;
}

Widget _harness({required double width, required Widget child}) {
  return MaterialApp(
    home: SingleChildScrollView(
      child: Center(
        child: SizedBox(width: width, child: child),
      ),
    ),
  );
}

void main() {
  group('ReaderLoadedPageImage', () {
    testWidgets(
      'lays out tall dimensionless pages at natural height '
      '(regression: AsuraScans strips were letterboxed into a 2/3 box)',
      (tester) async {
        // 10x300 image: 30x taller than wide, like an AsuraScans strip.
        final tallPng = buildPng(10, 300);
        final provider = MemoryImage(tallPng);

        await tester.runAsync(() async {
          await tester.pumpWidget(
            _harness(
              width: 100,
              child: ReaderLoadedPageImage(
                image: provider,
                fitMode: ReaderFitMode.width,
                semanticLabel: 'page',
              ),
            ),
          );
          // Let the image decode and the layout settle.
          await precacheImage(
            provider,
            tester.element(find.byType(ReaderLoadedPageImage)),
          );
        });
        await tester.pumpAndSettle();

        final size = tester.getSize(find.byType(ReaderLoadedPageImage));
        expect(size.width, 100);
        // Natural height at width 100 is 100 * (300 / 10) = 3000. The old bug
        // squeezed the whole image inside a width * 3/2 box instead.
        expect(size.height, moreOrLessEquals(3000, epsilon: 1));
      },
    );

    testWidgets('keeps ~2/3 pages at their natural height too', (tester) async {
      final png = buildPng(20, 30);
      final provider = MemoryImage(png);

      await tester.runAsync(() async {
        await tester.pumpWidget(
          _harness(
            width: 100,
            child: ReaderLoadedPageImage(
              image: provider,
              fitMode: ReaderFitMode.width,
              semanticLabel: 'page',
            ),
          ),
        );
        await precacheImage(
          provider,
          tester.element(find.byType(ReaderLoadedPageImage)),
        );
      });
      await tester.pumpAndSettle();

      final size = tester.getSize(find.byType(ReaderLoadedPageImage));
      expect(size.height, moreOrLessEquals(150, epsilon: 1));
    });
  });

  group('ReaderPageImage placeholder', () {
    testWidgets('reserves a 2/3 box only while loading', (tester) async {
      await tester.pumpWidget(
        _harness(
          width: 90,
          child: const ReaderPageImage(
            imageUrl: 'http://127.0.0.1:1/never-loads.png',
            alt: 'page',
            aspectRatio: 2 / 3,
            fitMode: ReaderFitMode.width,
          ),
        ),
      );
      await tester.pump();

      // While loading, the placeholder keeps the fallback ratio so the list
      // reserves space; the loaded image path is covered above.
      final size = tester.getSize(find.byType(ReaderPageImage));
      expect(size.width, 90);
      expect(size.height, moreOrLessEquals(135, epsilon: 1));
    });
  });
}