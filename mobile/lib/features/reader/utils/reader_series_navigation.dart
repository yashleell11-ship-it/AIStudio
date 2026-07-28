import 'package:flutter/widgets.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';

/// Opens the library series page for the chapter currently being read.
///
/// The reader route already carries the series id, so this never needs a
/// lookup — see [ReaderScreen].
void openLibrarySeriesFromReader(BuildContext context, int seriesId) {
  _openSeriesFromReader(
    context,
    routePattern: Routes.seriesDetail,
    pathParameters: {'seriesId': seriesId.toString()},
    location: RoutePaths.seriesDetail(seriesId),
  );
}

/// Opens the source series page for the chapter currently being read.
///
/// [seriesId] is the raw connector id; [RoutePaths.sourceSeriesDetail] does the
/// percent-encoding, so ids containing `/` survive the trip.
void openSourceSeriesFromReader(
  BuildContext context, {
  required String sourceId,
  required String seriesId,
}) {
  _openSeriesFromReader(
    context,
    routePattern: Routes.sourceSeriesDetail,
    pathParameters: {'sourceId': sourceId, 'seriesId': seriesId},
    location: RoutePaths.sourceSeriesDetail(sourceId, seriesId),
  );
}

/// Jumps from an open chapter to the series page listing every chapter.
///
/// Two strategies, and which one applies is not a matter of taste:
///
///  * **Pop** when the series page is already the route directly beneath the
///    reader. That is the common case — both series screens `push` the reader
///    on top of themselves, and every `go` to a nested reader location builds
///    the series page underneath it — so returning to the live page keeps the
///    back stack exactly as it was. Pushing a second copy instead would grow
///    the stack on every chapter → series → chapter round trip.
///
///  * **Go** otherwise, i.e. when the reader was pushed from somewhere that is
///    not the series page (Continue reading, bookmarks, a deep link). The
///    series page *cannot* be pushed on top of the reader: the reader route
///    declares `parentNavigatorKey: rootNavigatorKey` so it renders above the
///    tab shell, while series detail lives inside it. go_router answers a push
///    for a shell route from above the shell by appending a second
///    `ShellRouteMatch` to the root navigator, and both carry the same page
///    key — `Navigator` asserts on the duplicate and the screen goes blank.
///    `go` rebuilds the stack from the series location instead. It does not
///    strand anyone: series detail is nested under its tab root, so the rebuilt
///    stack is still poppable and the iOS edge-swipe keeps working from there.
void _openSeriesFromReader(
  BuildContext context, {
  required String routePattern,
  required Map<String, String> pathParameters,
  required String location,
}) {
  if (context.canPop() &&
      _seriesSitsBeneathReader(
        context,
        routePattern: routePattern,
        pathParameters: pathParameters,
      )) {
    context.pop();
    return;
  }
  context.go(location);
}

/// Whether [routePattern] with [pathParameters] is what the reader would return
/// to if it were popped right now.
///
/// Asks go_router the same way a pop does — drop the leaf match and look at
/// what is left — then compares the route *pattern* and its path parameters
/// rather than the resulting location. The match list reports parameters
/// decoded (`toonily/series-a`) while the locations we build are percent-
/// encoded (`toonily%2Fseries-a`), so comparing location strings would report
/// two spellings of the same series as different.
bool _seriesSitsBeneathReader(
  BuildContext context, {
  required String routePattern,
  required Map<String, String> pathParameters,
}) {
  final configuration = GoRouter.of(context).routerDelegate.currentConfiguration;
  final leaf = configuration.lastOrNull;
  if (leaf == null) return false;

  final beneath = configuration.remove(leaf);
  if (beneath.isEmpty || beneath.fullPath != routePattern) return false;

  return pathParameters.entries.every(
    (parameter) => beneath.pathParameters[parameter.key] == parameter.value,
  );
}
