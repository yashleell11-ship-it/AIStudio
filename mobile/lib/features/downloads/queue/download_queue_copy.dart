/// The one wording for "why is the queue not moving" and "why does it stop
/// when I leave the app", shared by the Downloads screen's live panel and the
/// per-series progress card on a series page.
///
/// Both surfaces answer the same owner question from different places, and a
/// user who reads one explanation on the series page and a differently-worded
/// one in Downloads has been told two things, not one.
library;

import 'package:manhwamaniacs/features/downloads/models/storage_cap.dart';
import 'package:manhwamaniacs/features/downloads/queue/download_queue_controller.dart';

/// Why the queue is sitting still, in words, or `null` for the reasons the
/// queue clears by itself — backgrounded (explained everywhere it can happen
/// by [kForegroundOnlyDownloadsNote]) and no-scope, which the UI already
/// answers by hiding the download controls entirely.
String? downloadPauseMessage(DownloadQueuePauseReason reason, StorageCap cap) {
  return switch (reason) {
    DownloadQueuePauseReason.userPaused =>
      'Paused by you. Nothing was lost — resuming carries on from the page '
          'it stopped at.',
    DownloadQueuePauseReason.freeSpaceFloor =>
      'Paused because this phone is almost full. Downloads stop before the '
          'last ~1.5 GB so the rest of your phone keeps working — delete '
          'something on the device to carry on.',
    DownloadQueuePauseReason.cap => cap == StorageCap.unlimited
        ? 'Paused at your download limit.'
        : 'Paused because downloads have filled your ${cap.label} limit. '
            'Raise the limit or free up space in Downloads → Storage.',
    DownloadQueuePauseReason.backgrounded ||
    DownloadQueuePauseReason.noScope ||
    DownloadQueuePauseReason.none =>
      null,
  };
}

/// Stated wherever a download can look frozen. A sideloaded build has no
/// dependable background execution (spec §3), so leaving the app really does
/// stop the queue — saying so is the difference between a designed limit and
/// what reads as a hang.
const String kForegroundOnlyDownloadsNote =
    'Downloads only run while ManhwaManiacs is open — leaving the app pauses '
    'them, and coming back picks up exactly where they stopped.';
