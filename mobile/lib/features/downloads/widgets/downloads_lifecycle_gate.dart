import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/downloads/providers/currently_open_chapter_provider.dart';
import 'package:manhwamaniacs/features/downloads/providers/progress_outbox_provider.dart';
import 'package:manhwamaniacs/features/downloads/providers/retention_maintenance_provider.dart';
import 'package:manhwamaniacs/features/downloads/providers/storage_settings_provider.dart';
import 'package:manhwamaniacs/features/downloads/queue/download_queue_controller.dart';
import 'package:manhwamaniacs/features/ocr/controllers/ocr_run_controller.dart';

/// Wraps the app and drives every piece of 1c-M3 that has to run on a
/// schedule rather than in response to a single user action:
///
/// - **Retention sweep** (read-then-expire) on launch and on every resume —
///   never on a timer, because a sideloaded build has no dependable
///   background execution (spec §3): "48 hours later" honestly means "the
///   first app open after 48 hours have elapsed".
/// - **Download queue resume** on launch (picks up any `queued`/`downloading`
///   row a previous run left behind) and **foreground gating** — paused the
///   instant the app backgrounds, resumed the instant it returns, so a
///   chapter mid-download is a durable, resumable no-op rather than a
///   silent stall.
/// - **Progress outbox flush** on launch, resume, and connectivity regained
///   — a save made offline reaches the server the moment any of those give
///   it a chance, without the reader itself ever blocking on it.
///
/// Mounted once at the app root (`app.dart`), the same place
/// `WhatsNewAutoShow` hooks the identical `WidgetsBindingObserver` pattern.
class DownloadsLifecycleGate extends ConsumerStatefulWidget {
  const DownloadsLifecycleGate({super.key, required this.child});

  final Widget child;

  @override
  ConsumerState<DownloadsLifecycleGate> createState() => _DownloadsLifecycleGateState();
}

class _DownloadsLifecycleGateState extends ConsumerState<DownloadsLifecycleGate>
    with WidgetsBindingObserver {
  StreamSubscription<List<ConnectivityResult>>? _connectivitySubscription;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _connectivitySubscription = Connectivity().onConnectivityChanged.listen((results) {
      if (results.any((r) => r != ConnectivityResult.none)) {
        _flushOutbox();
      }
    });
    WidgetsBinding.instance.addPostFrameCallback((_) => _onActive(isLaunch: true));
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final controller = ref.read(downloadQueueControllerProvider.notifier);
    final ocr = ref.read(ocrRunControllerProvider.notifier);
    if (state == AppLifecycleState.resumed) {
      controller.setForeground(true);
      ocr.setForeground(true);
      _onActive(isLaunch: false);
    } else {
      // Foreground-only downloads (spec §3): pause before the queue's next
      // network call rather than let it race an app that's about to suspend.
      controller.setForeground(false);
      // Same for an in-flight OCR run (spec §4) — it holds between pages
      // rather than being cancelled, so nothing already recognized is lost.
      ocr.setForeground(false);
    }
  }

  void _onActive({required bool isLaunch}) {
    if (!mounted) return;
    _sweep();
    ref.read(downloadQueueControllerProvider.notifier).resumePendingOnLaunch();
    _flushOutbox();
  }

  Future<void> _sweep() async {
    final interval = ref.read(retentionIntervalProvider).duration;
    final openChapter = ref.read(currentlyOpenChapterProvider);
    try {
      await ref.read(retentionMaintenanceProvider).sweepExpired(
            interval: interval,
            excludeOpen: openChapter,
          );
    } catch (_) {
      // Best-effort housekeeping — retried on the next launch/resume.
    }
  }

  void _flushOutbox() {
    unawaited(ref.read(progressOutboxControllerProvider).flush());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    unawaited(_connectivitySubscription?.cancel());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
