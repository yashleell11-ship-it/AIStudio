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

  /// Marks bytes mid-write: `<hash>.part<random>` beside the blob it is about
  /// to become. Recognised by [sweepInterruptedWrites], so a write a kill
  /// interrupted is reclaimable rather than a file nothing will ever look at
  /// again.
  static const String _tempMarker = '.part';

  /// A blob's own name: sha256, lowercase hex. The orphan sweep walks real
  /// directories, so it needs to be able to say which files in there are
  /// blobs it wrote and which are not its business.
  static final RegExp _blobName = RegExp(r'^[0-9a-f]{64}$');

  /// The content-addressed name [bytes] will be stored under, without
  /// touching the disk. Split out because `DownloadsStore.savePage` has to
  /// know the hash *before* it knows whether the row that would reference it
  /// is accepted (`downloads_store.dart`) — writing first is what leaves a
  /// file nothing points at.
  static String hashOf(List<int> bytes) => sha256.convert(bytes).toString();

  /// Hashes [bytes], writes them to their content-addressed path if not
  /// already present, and returns the hash + final size. Idempotent: calling
  /// this twice with identical bytes is a cheap no-op the second time —
  /// including two *concurrent* calls (the download queue fetches pages at
  /// `kPageFetchConcurrency`, and two different page numbers can legitimately
  /// hash to the same content, e.g. a shared "loading" placeholder image).
  Future<({String hash, int size})> write(List<int> bytes) async {
    final hash = hashOf(bytes);
    await writeHashed(hash, bytes);
    return (hash: hash, size: bytes.length);
  }

  /// [write] for a caller that already hashed the bytes — same guarantees,
  /// one sha256 pass instead of two. [hash] must be [hashOf] of [bytes]: the
  /// tree is content-addressed and nothing re-verifies it here.
  Future<void> writeHashed(String hash, List<int> bytes) async {
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
      final tmp = File('${file.path}$_tempMarker${_rng.nextInt(1 << 32)}');
      await tmp.writeAsBytes(bytes, flush: true);
      await tmp.rename(file.path);
    }
  }

  /// Every blob on disk that has sat untouched for [untouchedFor], by hash —
  /// what the orphan reclaim in `RetentionMaintenance.reclaimOrphanBlobs`
  /// compares against the index. Interrupted writes are not blobs and are
  /// left to [sweepInterruptedWrites]; so is anything else that found its way
  /// into the tree, since a user can drop files here through the Files app.
  ///
  /// The age margin keeps the reclaim off files that are still being wired
  /// up: a caller deciding "this hash has no row" about bytes written seconds
  /// ago is answering a question about work in flight.
  Future<List<String>> hashesOnDisk({
    Duration untouchedFor = Duration.zero,
  }) async {
    if (!rootDirectory.existsSync()) return const [];
    final cutoff = DateTime.now().subtract(untouchedFor);
    final hashes = <String>[];
    await for (final entity in rootDirectory.list(
      recursive: true,
      followLinks: false,
    )) {
      if (entity is! File) continue;
      final name = p.basename(entity.path);
      if (!_blobName.hasMatch(name)) continue;
      try {
        if (untouchedFor > Duration.zero &&
            entity.statSync().modified.isAfter(cutoff)) {
          continue;
        }
      } catch (_) {
        continue; // Deleted between the listing and the stat — already gone.
      }
      hashes.add(name);
    }
    return hashes;
  }

  /// Removes the `.part` files left behind by writes that never reached their
  /// rename — a kill mid-download, or the OS reclaiming the process. Returns
  /// how many it removed.
  ///
  /// Only files untouched for [olderThan]: a young temp file is far more
  /// likely to belong to a write happening *right now* (the queue fetches
  /// several pages at once), and deleting one out from under its own writer
  /// would turn a working download into a failed one.
  Future<int> sweepInterruptedWrites({
    Duration olderThan = const Duration(hours: 1),
  }) async {
    if (!rootDirectory.existsSync()) return 0;
    final cutoff = DateTime.now().subtract(olderThan);
    var removed = 0;
    await for (final entity in rootDirectory.list(
      recursive: true,
      followLinks: false,
    )) {
      if (entity is! File) continue;
      if (!p.basename(entity.path).contains(_tempMarker)) continue;
      try {
        if (entity.statSync().modified.isAfter(cutoff)) continue;
        await entity.delete();
        removed++;
      } catch (_) {
        // Gone already, or its writer got there first — nothing to fix.
      }
    }
    return removed;
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
