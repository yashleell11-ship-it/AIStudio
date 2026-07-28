import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/features/downloads/models/queue_download_response.dart';

/// How long a queue confirmation is allowed to sit on screen.
///
/// Deliberately far shorter than Flutter's 4s default. The owner photographed a
/// "Queued 1 chapter" bar parked over the page he was reading; a confirmation
/// that outlives the glance it is meant for is just an obstruction.
const Duration queueDownloadSnackBarDuration = Duration(milliseconds: 1500);

String queueDownloadFeedbackMessage(QueueDownloadResponse response) {
  final queued = response.queued.length;
  final skipped = response.skipped.length;
  final parts = <String>[];

  if (queued > 0) {
    parts.add('Queued $queued chapter${queued == 1 ? '' : 's'}');
  }
  if (skipped > 0) {
    parts.add('Skipped $skipped already downloaded');
  }
  if (parts.isEmpty) {
    return 'No chapters queued';
  }
  return parts.join('\n');
}

/// True for the two reader destinations —
/// `/library/:seriesId/chapters/:chapterId/read` and
/// `/sources/:sourceId/series/:seriesId/chapters/:chapterId/read`.
///
/// Matched on shape rather than against `Routes.reader`/`Routes.sourceReader`
/// because those are *patterns* with `:params`, not concrete locations. Query
/// and fragment are stripped by hand instead of via `Uri.parse`: source series
/// and chapter ids are percent-encoded opaque strings (see `RoutePaths`), and a
/// malformed escape would make `Uri.parse` throw on what is only a "should I
/// stay quiet?" check.
bool isReaderRoute(String location) {
  final path = location.split('?').first.split('#').first;
  return path.endsWith('/read') && path.contains('/chapters/');
}

/// Whether a queue result is worth interrupting the user for at all.
///
/// Queueing exactly one chapter needs no banner: the row the user just tapped
/// already flips to its downloading/queued state, and that in-place change is a
/// better confirmation than a bar over the content — it points at the thing
/// that changed. Everything else still gets a (brief) word, because nothing
/// else on screen says it: a bulk queue collapses the selection UI, and
/// "skipped"/"nothing queued" outcomes have no row-level representation.
bool shouldShowQueueDownloadFeedback(QueueDownloadResponse response) {
  return !(response.queued.length == 1 && response.skipped.isEmpty);
}

/// Confirm a queue request — quietly, and never on top of the reader.
///
/// Three rules, all of them from the owner's report:
///  * silent when the tapped row already shows the state (see
///    [shouldShowQueueDownloadFeedback]);
///  * never shown while a chapter is open, and dismissed immediately if the
///    user navigates away from the screen that asked for it, so a bar queued on
///    a series page cannot follow them into the reader;
///  * never stacked — the root [ScaffoldMessenger] *queues* snack bars, so five
///    download taps used to mean five consecutive bars. Clearing first caps the
///    backlog at one.
void showQueueDownloadSnackBar(
  BuildContext context,
  QueueDownloadResponse response,
) {
  if (!shouldShowQueueDownloadFeedback(response)) return;

  // `maybeOf` rather than `of`: this helper is also reachable from widget tests
  // and any future host without a GoRouter above it, and a missing router must
  // not turn a confirmation into a crash.
  final router = GoRouter.maybeOf(context);
  final location = router?.routerDelegate.currentConfiguration.uri.toString();
  if (location != null && isReaderRoute(location)) return;

  final messenger = ScaffoldMessenger.of(context)..removeCurrentSnackBar();
  final controller = messenger.showSnackBar(
    SnackBar(
      content: Text(queueDownloadFeedbackMessage(response)),
      behavior: SnackBarBehavior.floating,
      duration: queueDownloadSnackBarDuration,
    ),
  );

  if (router == null) return;

  // The bar belongs to the screen that queued the download. Route changes are
  // the only signal available here (the caller's State may already be gone by
  // the time the queue POST resolves), so tear it down on the first one.
  final routeInformation = router.routeInformationProvider;
  var live = true;
  void handleRouteChange() {
    if (!live) return;
    live = false;
    routeInformation.removeListener(handleRouteChange);
    // `removeCurrentSnackBar` on the messenger, not `controller.close()`:
    // close() asserts that this controller is still the front of the queue,
    // which is not guaranteed once other code has shown its own bar.
    // Guarded on `mounted` because this fires from a router notification, which
    // can outlive the messenger during a teardown.
    if (messenger.mounted) messenger.removeCurrentSnackBar();
  }

  routeInformation.addListener(handleRouteChange);
  unawaited(
    controller.closed.then((_) {
      live = false;
      routeInformation.removeListener(handleRouteChange);
    }),
  );
}
