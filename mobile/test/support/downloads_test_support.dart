import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/downloads/models/download_concurrency.dart';
import 'package:manhwamaniacs/features/downloads/providers/storage_settings_provider.dart';
import 'package:manhwamaniacs/features/downloads/services/blob_store.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_db.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_store.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

/// `flutter test` runs on the desktop host, which has no sqflite platform
/// channel — every downloads test opens a real SQLite database via FFI
/// instead (backed by the system's libsqlite3), never a mock. Call once
/// before any test in a file touches the store.
void initSqfliteFfiForTests() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;
}

/// One throwaway store wired to an in-memory database and a temp-directory
/// blob tree — the temp dir is the test's responsibility to delete via
/// [TestDownloadsHarness.dispose].
class TestDownloadsHarness {
  TestDownloadsHarness._(this.tempDir, this._dbPath);

  final Directory tempDir;
  final String _dbPath;

  static Future<TestDownloadsHarness> create() async {
    final tempDir = await Directory.systemTemp.createTemp('mm-downloads-test-');
    final dbPath = '${tempDir.path}/downloads.db';
    return TestDownloadsHarness._(tempDir, dbPath);
  }

  Future<Database> openDatabase() => openDownloadsDatabase(overridePath: _dbPath);

  Future<BlobStore> openBlobStore() async {
    final dir = Directory('${tempDir.path}/blobs');
    return BlobStore(rootDirectory: dir);
  }

  /// A store for [scopeId] sharing this harness's database/blob tree —
  /// exactly how two profiles on one device share the real singletons.
  /// Synchronous (both fields are themselves `Future`s the store awaits
  /// lazily) so it can also be used directly as a `Provider` override value.
  DownloadsStore storeFor(String scopeId) => DownloadsStore(
        scopeId: scopeId,
        database: openDatabase(),
        blobStore: openBlobStore(),
      );

  Future<void> dispose() async {
    if (tempDir.existsSync()) await tempDir.delete(recursive: true);
  }
}

/// Pins how many chapters the queue downloads at once.
///
/// Every container that drives the real loop needs this for the same reason it
/// needs a pinned `storageCapProvider`: the notifier is preferences-backed and
/// these tests deliberately never stand up SharedPreferences. Defaults to
/// [DownloadConcurrency.one] so a test that is not *about* concurrency keeps
/// the strictly serial queue its assertions were written against.
Override downloadConcurrencyOverride([
  DownloadConcurrency value = DownloadConcurrency.one,
]) =>
    downloadConcurrencyProvider
        .overrideWith(() => _FixedDownloadConcurrencyNotifier(value));

class _FixedDownloadConcurrencyNotifier extends DownloadConcurrencyNotifier {
  _FixedDownloadConcurrencyNotifier(this._value);
  final DownloadConcurrency _value;

  @override
  DownloadConcurrency build() => _value;
}
