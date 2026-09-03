import 'dart:io';
import 'dart:math';

import 'package:crypto/crypto.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

/// The content-addressed blob tree: page bytes on disk, named by their own
/// sha256 hash so two profiles (or two chapters that happen to share a page)
/// store one copy.
///
/// Lives under `getApplicationDocumentsDirectory()` — deliberately **not**
/// Application Support and never Temporary — per spec §3b, so
/// `UIFileSharingEnabled` can surface it under *On My iPhone → ManhwaManiacs*
/// in the Files app. The sqflite index that references these files lives
/// elsewhere (`downloads_db.dart`), so a blob deleted by hand from Files is
/// merely orphaned (recoverable by re-downloading), never a corrupt index.
class BlobStore {
  BlobStore({required this.rootDirectory});

  /// `Documents/mm-store/blobs`.
  final Directory rootDirectory;

  static Future<BlobStore> forApplicationDocuments() async {
    final docs = await getApplicationDocumentsDirectory();
    return BlobStore(
      rootDirectory: Directory(p.join(docs.path, 'mm-store', 'blobs')),
    );
  }

  /// Deterministic path for a given hash — shards on the first two hex
  /// characters so no single directory ends up with tens of thousands of
  /// entries on a heavily-downloaded install.
  File pathFor(String hash) => File(
        p.join(rootDirectory.path, hash.substring(0, 2), hash),
      );

  static final Random _rng = Random();

  /// Hashes [bytes], writes them to their content-addressed path if not
  /// already present, and returns the hash + final size. Idempotent: calling
  /// this twice with identical bytes is a cheap no-op the second time —
  /// including two *concurrent* calls (the download queue fetches pages at
  /// `kPageFetchConcurrency`, and two different page numbers can legitimately
  /// hash to the same content, e.g. a shared "loading" placeholder image).
  Future<({String hash, int size})> write(List<int> bytes) async {
    final hash = sha256.convert(bytes).toString();
    final file = pathFor(hash);
    if (!file.existsSync()) {
      await file.parent.create(recursive: true);
      // Write to a per-call temp file, then rename — never a shared `.part`
      // name, so two concurrent writers racing to the same hash (identical
      // bytes) never write through the same temp file at once. Whichever
      // rename lands second just overwrites the first with identical bytes,
      // which is safe. A kill mid-write can never leave a truncated file at
      // the real content-addressed path — the hash only ever names a
      // complete blob.
      final tmp = File('${file.path}.part${_rng.nextInt(1 << 32)}');
      await tmp.writeAsBytes(bytes, flush: true);
      await tmp.rename(file.path);
    }
    return (hash: hash, size: bytes.length);
  }

  /// True when the blob file for [hash] both exists and is non-empty. A
  /// user can delete files from the Files app by hand — this is how a page
  /// resolver notices and falls back to network instead of serving a
  /// zero-byte image.
  bool exists(String hash) {
    final file = pathFor(hash);
    return file.existsSync() && file.lengthSync() > 0;
  }

  /// Best-effort delete — never throws. A blob already missing (user deleted
  /// it by hand) is not an error here; the caller only wanted it gone.
  Future<void> delete(String hash) async {
    try {
      final file = pathFor(hash);
      if (file.existsSync()) await file.delete();
    } catch (_) {
      // Orphaned index entry at worst — recoverable by re-download.
    }
  }
}
