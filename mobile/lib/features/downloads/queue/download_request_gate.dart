import 'dart:async';
import 'dart:collection';

/// A counting semaphore over the download queue's outbound requests.
///
/// Its whole purpose is that the user-facing chapter-concurrency setting
/// cannot multiply the request rate: chapters compete for these slots instead
/// of each bringing their own budget, so [kQueueRequestConcurrency] is the
/// worst case no matter how many chapters are in flight.
///
/// Only the network call is ever held — never a SQLite write, and never
/// another acquisition — so a slot is released promptly and no caller can
/// deadlock waiting on a slot it is itself holding.
class DownloadRequestGate {
  DownloadRequestGate(this.slots) : assert(slots > 0, 'need at least one slot');

  final int slots;

  int _inUse = 0;
  final Queue<Completer<void>> _waiting = Queue<Completer<void>>();

  /// Runs [body] once a slot is free, releasing it however [body] ends — a
  /// throw must not strand a slot, or one failed page permanently narrows the
  /// gate for every chapter after it.
  Future<T> run<T>(Future<T> Function() body) async {
    await _acquire();
    try {
      return await body();
    } finally {
      _release();
    }
  }

  Future<void> _acquire() {
    if (_inUse < slots) {
      _inUse++;
      return Future<void>.value();
    }
    final waiter = Completer<void>();
    _waiting.add(waiter);
    return waiter.future;
  }

  void _release() {
    if (_waiting.isEmpty) {
      _inUse--;
      return;
    }
    // Hand the slot straight to the next waiter rather than releasing and
    // re-taking it: FIFO keeps a chapter that has been waiting from being
    // starved by one that only just asked.
    _waiting.removeFirst().complete();
  }
}
