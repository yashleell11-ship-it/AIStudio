import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

/// Minimal reader for the archives [StoredZipWriter] produces — enough to
/// prove the bytes are a real ZIP rather than merely self-consistent: it
/// finds the end-of-central-directory record, walks the central directory,
/// and re-reads each entry through the *offset the directory recorded*, which
/// is exactly how a real extractor works and the thing a hand-rolled writer
/// is most likely to get wrong.
List<({String name, Uint8List bytes, int crc})> readStoredZip(Uint8List zip) {
  final data = ByteData.sublistView(zip);

  var eocd = zip.length - 22;
  while (eocd >= 0 && data.getUint32(eocd, Endian.little) != 0x06054B50) {
    eocd--;
  }
  expect(eocd, greaterThanOrEqualTo(0), reason: 'no EOCD record found');

  final count = data.getUint16(eocd + 10, Endian.little);
  var cursor = data.getUint32(eocd + 16, Endian.little);

  final entries = <({String name, Uint8List bytes, int crc})>[];
  for (var i = 0; i < count; i++) {
    expect(data.getUint32(cursor, Endian.little), 0x02014B50);
    final crc = data.getUint32(cursor + 16, Endian.little);
    final size = data.getUint32(cursor + 24, Endian.little);
    final nameLength = data.getUint16(cursor + 28, Endian.little);
    final localOffset = data.getUint32(cursor + 42, Endian.little);
    final name =
        ascii.decode(zip.sublist(cursor + 46, cursor + 46 + nameLength));

    expect(data.getUint32(localOffset, Endian.little), 0x04034B50);
    expect(
      data.getUint16(localOffset + 8, Endian.little),
      0,
      reason: 'entries must be stored, not deflated',
    );
    final localNameLength = data.getUint16(localOffset + 26, Endian.little);
    final extraLength = data.getUint16(localOffset + 28, Endian.little);
    final start = localOffset + 30 + localNameLength + extraLength;
    entries.add(
      (
        name: name,
        bytes: Uint8List.sublistView(zip, start, start + size),
        crc: crc,
      ),
    );
    cursor += 46 + nameLength;
  }
  return entries;
}
