/// Read-then-expire sweep interval — how long after a chapter is finished its
/// phone copy is deleted (server copy untouched). A constant per spec §3/3b,
/// but "surfaced in Settings so it can be changed or switched off".
enum RetentionInterval {
  off(null),
  hours24(Duration(hours: 24)),
  hours48(Duration(hours: 48)),
  days7(Duration(days: 7));

  const RetentionInterval(this.duration);

  /// `null` means the read-then-expire sweep never deletes anything —
  /// pressure eviction (Free up space / the cap) is still active.
  final Duration? duration;

  String get label => switch (this) {
        RetentionInterval.off => 'Off',
        RetentionInterval.hours24 => '24 hours',
        RetentionInterval.hours48 => '48 hours (default)',
        RetentionInterval.days7 => '7 days',
      };

  static RetentionInterval fromWire(String? value) =>
      RetentionInterval.values.firstWhere(
        (interval) => interval.name == value,
        orElse: () => RetentionInterval.hours48,
      );
}
