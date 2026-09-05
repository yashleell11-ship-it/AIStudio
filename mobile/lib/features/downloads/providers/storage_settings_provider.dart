import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/downloads/models/download_concurrency.dart';
import 'package:manhwamaniacs/features/downloads/models/retention_policy.dart';
import 'package:manhwamaniacs/features/downloads/models/storage_cap.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';

/// The on-device downloads cap — **per install**, not per profile (spec
/// §3b: two profiles share one physical disk). Backed by
/// [PreferencesService], the same untyped SharedPreferences store every other
/// device-level setting (theme, language, reader defaults) already uses.
final storageCapProvider =
    NotifierProvider<StorageCapNotifier, StorageCap>(
  StorageCapNotifier.new,
  name: 'storageCap',
);

class StorageCapNotifier extends Notifier<StorageCap> {
  @override
  StorageCap build() =>
      StorageCap.fromWire(ref.watch(preferencesProvider).downloadStorageCap);

  Future<void> setCap(StorageCap cap) async {
    state = cap;
    await ref.read(preferencesProvider).setDownloadStorageCap(cap.name);
  }
}

/// The read-then-expire sweep interval — also per install. "Off" (`null`
/// duration) disables the sweep without touching cap-pressure eviction.
final retentionIntervalProvider =
    NotifierProvider<RetentionIntervalNotifier, RetentionInterval>(
  RetentionIntervalNotifier.new,
  name: 'retentionInterval',
);

class RetentionIntervalNotifier extends Notifier<RetentionInterval> {
  @override
  RetentionInterval build() => RetentionInterval.fromWire(
        ref.watch(preferencesProvider).downloadRetentionInterval,
      );

  Future<void> setInterval(RetentionInterval interval) async {
    state = interval;
    await ref
        .read(preferencesProvider)
        .setDownloadRetentionInterval(interval.name);
  }
}

/// How many chapters the queue downloads at once — per install for the same
/// reason the cap is: one device, one connection to one server.
///
/// The queue reads this fresh on every pass rather than watching it, so a
/// change lands on the next batch instead of restarting the run mid-chapter.
final downloadConcurrencyProvider =
    NotifierProvider<DownloadConcurrencyNotifier, DownloadConcurrency>(
  DownloadConcurrencyNotifier.new,
  name: 'downloadConcurrency',
);

class DownloadConcurrencyNotifier extends Notifier<DownloadConcurrency> {
  @override
  DownloadConcurrency build() => DownloadConcurrency.fromWire(
        ref.watch(preferencesProvider).downloadConcurrency,
      );

  Future<void> setConcurrency(DownloadConcurrency value) async {
    state = value;
    await ref.read(preferencesProvider).setDownloadConcurrency(value.name);
  }
}
