import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:wakelock_plus/wakelock_plus.dart';

/// Keeps the device awake while the reader is open.
abstract class ReaderWakelock {
  Future<void> enable();
  Future<void> disable();
}

class PlatformReaderWakelock implements ReaderWakelock {
  @override
  Future<void> enable() => WakelockPlus.enable();

  @override
  Future<void> disable() => WakelockPlus.disable();
}

final readerWakelockProvider = Provider<ReaderWakelock>(
  (_) => PlatformReaderWakelock(),
  name: 'readerWakelock',
);
