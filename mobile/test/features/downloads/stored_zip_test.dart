import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/downloads/services/stored_zip.dart';

import '../../support/stored_zip_reader.dart';

Uint8List _build(
  Map<String, List<int>> files, {
  DateTime? modified,
}) {
  final out = BytesBuilder();
  final zip = StoredZipWriter(out.add, modified: modified);
  files.forEach(zip.addFile);
  zip.finish();
  final bytes = out.toBytes();
  expect(zip.bytesWritten, bytes.length);
  return bytes;
}

void main() {
  group('crc32', () {
    test('matches the standard check vectors', () {
      expect(crc32(ascii.encode('123456789')), 0xCBF43926);
      expect(crc32(const []), 0);
      expect(crc32(ascii.encode('The quick brown fox jumps over the lazy dog')),
          0x414FA339);
    });
  });

  group('StoredZipWriter', () {
    test('round-trips entries in order, byte for byte', () {
      final page1 = List<int>.generate(300, (i) => i % 256);
      final page2 = List<int>.generate(17, (i) => 255 - i);

      final entries = readStoredZip(
        _build({'001.jpg': page1, '002.png': page2}),
      );

      expect(entries.map((e) => e.name), ['001.jpg', '002.png']);
      expect(entries[0].bytes, page1);
      expect(entries[1].bytes, page2);
      expect(entries[0].crc, crc32(page1));
      expect(entries[1].crc, crc32(page2));
    });

    test('an empty archive is still a valid, readable ZIP', () {
      expect(readStoredZip(_build(const {})), isEmpty);
    });

    test('handles a zero-byte entry', () {
      final entries = readStoredZip(_build({'000.img': const <int>[]}));
      expect(entries.single.bytes, isEmpty);
      expect(entries.single.crc, 0);
    });

    test('clamps a pre-1980 device clock instead of wrapping the DOS date', () {
      // DOS dates have 7 bits of year counted from 1980; a phone whose clock
      // has reset would otherwise write a date that decodes as garbage.
      final zip = _build(
        {'001.jpg': const [1, 2, 3]},
        modified: DateTime(1970, 5, 6, 7, 8, 9),
      );
      final data = ByteData.sublistView(zip);
      final dosDate = data.getUint16(12, Endian.little);
      expect(dosDate >> 9, 0, reason: 'year clamped to 1980');
      expect((dosDate >> 5) & 0xF, 5);
      expect(dosDate & 0x1F, 6);
    });

    test('refuses to keep writing after finish', () {
      final out = BytesBuilder();
      final zip = StoredZipWriter(out.add)..finish();
      expect(() => zip.addFile('001.jpg', const [1]), throwsStateError);
      expect(zip.finish, throwsStateError);
    });
  });
}
