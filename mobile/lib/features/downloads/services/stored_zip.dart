import 'dart:convert';
import 'dart:typed_data';

/// A streaming ZIP writer that only ever *stores* (compression method 0) —
/// the container half of a CBZ export.
///
/// **Why hand-rolled rather than the `archive` package.** The only thing a
/// CBZ holds here is page images that are already JPEG/PNG/WebP; deflating
/// them a second time buys nothing measurable and costs phone CPU, so
/// "store" is the correct method and a store-only writer is small enough to
/// own outright. That keeps the dependency graph exactly as `pubspec.lock`
/// pins it, which matters more than usual on this project: the iOS build
/// runs on a throwaway cloud Mac nobody can debug interactively (see the
/// SwiftPM note in `pubspec.yaml`).
///
/// **Streaming, not buffering.** Entries are handed straight to [_write] as
/// they arrive, so peak memory is one page — not the whole archive. A
/// sixty-page chapter would otherwise be held twice over on a device with no
/// swap.
///
/// No Zip64 and no data descriptors: one manga chapter is a handful of MB
/// and a few dozen entries, so the classic format's 4 GB / 65535-entry
/// ceilings are unreachable here. [addFile] throws rather than emit a
/// silently-corrupt archive if that ever stops being true.
class StoredZipWriter {
  /// [write] receives every byte of the archive in order — `IOSink.add` for a
  /// real file, a `BytesBuilder.add` in tests. [modified] stamps every entry
  /// (DOS timestamps have 2-second resolution, hence the halving below).
  StoredZipWriter(this._write, {DateTime? modified})
      : _stamp = modified ?? DateTime.now();

  final void Function(List<int> chunk) _write;
  final DateTime _stamp;
  final List<_ZipEntry> _entries = [];

  var _offset = 0;
  var _finished = false;

  /// Bytes emitted so far. Equal to the final archive size once [finish] has
  /// run.
  int get bytesWritten => _offset;

  /// Appends one stored entry. [name] must be ASCII — every caller here
  /// generates its own zero-padded `001.jpg`-style names, so a non-ASCII name
  /// means a bug rather than a user with an unusual title, and encoding it as
  /// Latin-1 without the UTF-8 flag would produce mojibake in the extractor.
  void addFile(String name, List<int> bytes) {
    if (_finished) {
      throw StateError('Cannot add to a finished archive');
    }
    if (_entries.length >= 0xFFFF) {
      throw StateError('Too many entries for a non-Zip64 archive');
    }
    if (bytes.length > 0xFFFFFFFF || _offset > 0xFFFFFFFF) {
      throw StateError('Archive too large for a non-Zip64 archive');
    }
    final nameBytes = ascii.encode(name);

    final crc = crc32(bytes);
    final header = ByteData(30)
      ..setUint32(0, 0x04034B50, Endian.little) // local file header signature
      ..setUint16(4, 20, Endian.little) // version needed to extract (2.0)
      ..setUint16(6, 0, Endian.little) // general purpose flags
      ..setUint16(8, 0, Endian.little) // method: stored
      ..setUint16(10, _dosTime, Endian.little)
      ..setUint16(12, _dosDate, Endian.little)
      ..setUint32(14, crc, Endian.little)
      ..setUint32(18, bytes.length, Endian.little) // compressed size
      ..setUint32(22, bytes.length, Endian.little) // uncompressed size
      ..setUint16(26, nameBytes.length, Endian.little)
      ..setUint16(28, 0, Endian.little); // extra field length

    _entries.add(
      _ZipEntry(
        nameBytes: nameBytes,
        crc: crc,
        size: bytes.length,
        localHeaderOffset: _offset,
      ),
    );

    _emit(header.buffer.asUint8List());
    _emit(nameBytes);
    _emit(bytes);
  }

  /// Writes the central directory and end-of-central-directory record. Must
  /// be called exactly once, after the last [addFile]; the archive is not a
  /// valid ZIP without it.
  void finish() {
    if (_finished) throw StateError('Archive already finished');
    _finished = true;

    final directoryOffset = _offset;
    for (final entry in _entries) {
      final record = ByteData(46)
        ..setUint32(0, 0x02014B50, Endian.little) // central directory header
        ..setUint16(4, 20, Endian.little) // version made by
        ..setUint16(6, 20, Endian.little) // version needed to extract
        ..setUint16(8, 0, Endian.little) // general purpose flags
        ..setUint16(10, 0, Endian.little) // method: stored
        ..setUint16(12, _dosTime, Endian.little)
        ..setUint16(14, _dosDate, Endian.little)
        ..setUint32(16, entry.crc, Endian.little)
        ..setUint32(20, entry.size, Endian.little) // compressed size
        ..setUint32(24, entry.size, Endian.little) // uncompressed size
        ..setUint16(28, entry.nameBytes.length, Endian.little)
        ..setUint16(30, 0, Endian.little) // extra field length
        ..setUint16(32, 0, Endian.little) // file comment length
        ..setUint16(34, 0, Endian.little) // disk number start
        ..setUint16(36, 0, Endian.little) // internal attributes
        ..setUint32(38, 0, Endian.little) // external attributes
        ..setUint32(42, entry.localHeaderOffset, Endian.little);
      _emit(record.buffer.asUint8List());
      _emit(entry.nameBytes);
    }
    final directorySize = _offset - directoryOffset;

    final end = ByteData(22)
      ..setUint32(0, 0x06054B50, Endian.little) // EOCD signature
      ..setUint16(4, 0, Endian.little) // this disk number
      ..setUint16(6, 0, Endian.little) // disk with central directory
      ..setUint16(8, _entries.length, Endian.little) // entries on this disk
      ..setUint16(10, _entries.length, Endian.little) // entries total
      ..setUint32(12, directorySize, Endian.little)
      ..setUint32(16, directoryOffset, Endian.little)
      ..setUint16(20, 0, Endian.little); // archive comment length
    _emit(end.buffer.asUint8List());
  }

  void _emit(List<int> chunk) {
    _write(chunk);
    _offset += chunk.length;
  }

  int get _dosTime =>
      (_stamp.hour << 11) | (_stamp.minute << 5) | (_stamp.second ~/ 2);

  /// DOS dates count years from 1980 in 7 bits. A device clock outside that
  /// window is clamped rather than allowed to wrap into a nonsense date.
  int get _dosDate =>
      ((_stamp.year - 1980).clamp(0, 127) << 9) |
      (_stamp.month << 5) |
      _stamp.day;
}

class _ZipEntry {
  const _ZipEntry({
    required this.nameBytes,
    required this.crc,
    required this.size,
    required this.localHeaderOffset,
  });

  final Uint8List nameBytes;
  final int crc;
  final int size;
  final int localHeaderOffset;
}

/// CRC-32 (IEEE 802.3, reflected) — the checksum every ZIP entry header
/// carries. `crypto` ships SHA/MD5 only, and this is the one place the app
/// needs a CRC.
int crc32(List<int> bytes) {
  var crc = 0xFFFFFFFF;
  for (final byte in bytes) {
    crc = _crcTable[(crc ^ byte) & 0xFF] ^ (crc >> 8);
  }
  return (crc ^ 0xFFFFFFFF) & 0xFFFFFFFF;
}

final Uint32List _crcTable = _buildCrcTable();

Uint32List _buildCrcTable() {
  final table = Uint32List(256);
  for (var i = 0; i < 256; i++) {
    var value = i;
    for (var bit = 0; bit < 8; bit++) {
      value = (value & 1) != 0 ? 0xEDB88320 ^ (value >> 1) : value >> 1;
    }
    table[i] = value;
  }
  return table;
}
