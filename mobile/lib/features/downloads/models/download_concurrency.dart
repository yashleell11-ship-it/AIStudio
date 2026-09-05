/// How many chapters the download queue fetches at the same time — a
/// **per-install** device property alongside [StorageCap] and
/// [RetentionInterval], not a per-profile one: every profile on this phone
/// talks to the same server over the same connection, so the number that
/// matters is "how hard does this device push", not "who is signed in".
///
/// Deliberately a short ladder rather than a free number. The ceiling is not
/// the phone's, it is the server's: the backend rate-limits the page-image
/// proxy on its `sources` bucket, holds one connector instance per source with
/// a shared 0.21 s `min_interval`, and sizes its own upstream fan-out at 4
/// workers (`services/bulk_fetch.py`, whose comment names the reason — "the
/// box has 2 vCPU and these threads each hold an upstream socket"). Three is
/// the point past which more chapters stop buying throughput and only buy
/// queueing, because [kQueueRequestConcurrency] is the real ceiling and two
/// chapters already saturate it.
enum DownloadConcurrency {
  one(1),
  two(2),
  three(3);

  const DownloadConcurrency(this.chapters);

  /// How many chapters may be mid-download at once.
  final int chapters;

  String get label => switch (this) {
        DownloadConcurrency.one => '1 chapter',
        DownloadConcurrency.two => '2 chapters (default)',
        DownloadConcurrency.three => '3 chapters',
      };

  /// [two] rather than [one]: one step up from the strictly-serial behaviour
  /// every build before this one had, which is a real speed-up the request
  /// asked for, while leaving the top of the ladder as something the user
  /// opts into rather than inherits.
  static DownloadConcurrency fromWire(String? value) =>
      DownloadConcurrency.values.firstWhere(
        (option) => option.name == value,
        orElse: () => DownloadConcurrency.two,
      );
}
