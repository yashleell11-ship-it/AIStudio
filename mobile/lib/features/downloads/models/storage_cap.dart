/// The on-device download cap — a **per-install** device property (not
/// per-profile: two profiles on the same phone share one physical disk), per
/// spec §3b.
enum StorageCap {
  gb2(2),
  gb5(5),
  gb10(10),
  gb20(20),
  unlimited(null);

  const StorageCap(this._gb);

  final int? _gb;

  /// Cap in bytes, or `null` for [unlimited] — callers must treat `null` as
  /// "no cap" rather than zero.
  int? get bytes => _gb == null ? null : _gb * 1024 * 1024 * 1024;

  String get label => switch (this) {
        StorageCap.gb2 => '2 GB',
        StorageCap.gb5 => '5 GB',
        StorageCap.gb10 => '10 GB',
        StorageCap.gb20 => '20 GB',
        StorageCap.unlimited => 'Unlimited',
      };

  static StorageCap fromWire(String? value) => StorageCap.values.firstWhere(
        (cap) => cap.name == value,
        orElse: () => StorageCap.gb10,
      );
}
