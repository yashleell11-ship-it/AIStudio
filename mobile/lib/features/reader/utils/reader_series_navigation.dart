import 'package:flutter/widgets.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';

/// Jumps from an open chapter to the series page listing every chapter.
///
/// Every reader — the manifest-driven library reader and the source-browsing
/// reader alike — opens a `(sourceId, seriesKey)` chapter and has no
/// dependable way to know a follow row's id (continue-reading, bookmarks and
/// history entry points carry only the source triple), so the series page to
/// land on is always [RoutePaths.sourceSeriesDetail] — the one series screen
/// reachable from just `(sourceId, seriesKey)`.
///
/// Two strategies, and which one applies is not a matter of taste:
///
///  * **Pop** when a series page is already the route directly beneath the
///    reader. That is the common case — both the followed series page
///    (`Routes.seriesDetail`) and the source-browse series page
///    (`Routes.sourceSeriesDetail`) `push` the reader on top of themselves —
///    so returning to the live page keeps the back stack exactly as it was
///    and preserves whatever richer (favorite/progress) state that page
///    already had loaded. Pushing a second copy instead would grow the stack
///    on every chapter → series → chapter round trip. The followed page
///    carries no comparable id to check here, so its pattern alone decides;
///    the source-browse page's `(sourceId, seriesKey)` is known and checked
///    exactly, so popping onto an unrelated source series never happens.
///
///  * **Go** otherwise, i.e. when the reader was pushed from somewhere that is
///    not a series page (Continue reading, bookmarks, history, a deep link).
///    The series page *cannot* be pushed on top of the reader: the reader
///    route declares `parentNavigatorKey: rootNavigatorKey` so it renders
///    above the tab shell, while series detail lives inside it. go_router
///    answers a push for a shell route from above the shell by appending a
///    second `ShellRouteMatch` to the root navigator, and both carry the same
///    page key — `Navigator` asserts on the duplicate and the screen goes
///    blank. `go` rebuilds the stack from the series location instead. It
///    does not strand anyone: series detail is nested under its tab root, so
///    the rebuilt stack is still poppable and the iOS edge-swipe keeps
///    working from there.
///
/// [seriesKey] is the raw connector key; [RoutePaths.sourceSeriesDetail] does
/// the percent-encoding, so keys containing `/` survive the trip.
void openSeriesFromReader(
  BuildContext context, {
  required String sourceId,
  required String seriesKey,
}) {
  if (context.canPop() && _seriesSitsBeneathReader(context, sourceId: sourceId, seriesKey: seriesKey)) {
    context.pop();
    return;
  }
  context.go(RoutePaths.sourceSeriesDetail(sourceId, seriesKey));
}

/// Leaves an open chapter — the Back button, the Android back gesture and the
/// hardware key all land here.
///
/// Back is not "go to the series page": it is "undo the step that opened
/// this", so a reader reached from Bookmarks belongs back in Bookmarks. A bare
/// `context.pop()` says that correctly, right up until the reader has moved
/// between chapters — which every reader does with `go` rather than `push`, so
/// that a thirty-chapter sitting does not build a thirty-deep stack to walk
/// back down.
///
/// `go` rebuilds the whole stack from the target location, and what it rebuilds
/// beneath the reader is whatever the ROUTE TREE puts there — not what the
/// reader was pushed from. The manga readers are nested (under the library tab
/// root and under the source series page), so a shell is always rebuilt under
/// them and `pop` still has a destination. The novel reader is registered
/// top-level (see [Routes.novelReader]), so after a chapter change it is the
/// entire stack: `pop` throws `GoError('There is nothing to pop')` and does
/// nothing visible, and the system back gesture — finding nothing to pop
/// either — closes the app mid-book.
///
/// So: pop when there is something to pop, and otherwise land on the series
/// page, the one destination reachable from the `(sourceId, seriesKey)` pair
/// every reader carries (see [openSeriesFromReader] for why that is
/// [RoutePaths.sourceSeriesDetail] for prose and pictures alike). Which is what
/// "Back always leaves the reader" was supposed to mean all along.
void leaveReader(
  BuildContext context, {
  required String sourceId,
  required String seriesKey,
}) {
  if (context.canPop()) {
    context.pop();
    return;
  }
  context.go(RoutePaths.sourceSeriesDetail(sourceId, seriesKey));
}

/// Whether a series page for `(sourceId, seriesKey)` is what the reader would
/// return to if it were popped right now.
///
/// Asks go_router the same way a pop does — drop the leaf match and look at
/// what is left — then compares the route *pattern* and its path parameters
/// rather than the resulting location. The match list reports parameters
/// decoded (`toonily/series-a`) while the locations we build are percent-
/// encoded (`toonily%2Fseries-a`), so comparing location strings would report
/// two spellings of the same series as different.
bool _seriesSitsBeneathReader(
  BuildContext context, {
  required String sourceId,
  required String seriesKey,
}) {
  final configuration = GoRouter.of(context).routerDelegate.currentConfiguration;
  final leaf = configuration.lastOrNull;
  if (leaf == null) return false;

  final beneath = configuration.remove(leaf);
  if (beneath.isEmpty) return false;

  if (beneath.fullPath == Routes.seriesDetail) return true;

  if (beneath.fullPath == Routes.sourceSeriesDetail) {
    return beneath.pathParameters['sourceId'] == sourceId &&
        beneath.pathParameters['seriesId'] == seriesKey;
  }

  return false;
}
