import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/novels/models/novel_typography.dart';

/// Loads the app's real bundled fonts into the test engine.
///
/// Call from `setUpAll`, never from inside a `testWidgets` body: a test body
/// runs in `FakeAsync`, where a `dart:io` future (`File.readAsBytes`) never
/// completes and the load hangs until the suite times out. The file reads here
/// are synchronous for the same reason.
///
/// Without this every glyph in a captured PNG is a box — `flutter_tester` ships
/// no system fonts, so an unresolved family falls back to the placeholder test
/// font. The families and asset paths mirror `pubspec.yaml`'s `fonts:` block.
Future<void> loadAppFonts() async {
  const families = <String, List<String>>{
    'Syne': ['assets/fonts/Syne.ttf'],
    'DMSans': ['assets/fonts/DMSans.ttf'],
    'Inter': [
      'assets/fonts/Inter-Regular.ttf',
      'assets/fonts/Inter-Medium.ttf',
      'assets/fonts/Inter-SemiBold.ttf',
      'assets/fonts/Inter-Bold.ttf',
    ],
    'BebasNeue': ['assets/fonts/BebasNeue-Regular.ttf'],
    'SpaceMono': ['assets/fonts/SpaceMono-Regular.ttf'],
  };
  for (final entry in families.entries) {
    final loader = FontLoader(entry.key);
    for (final path in entry.value) {
      final bytes = File(path).readAsBytesSync();
      loader.addFont(Future.value(ByteData.view(bytes.buffer)));
    }
    await loader.load();
  }
  await _loadMaterialIcons();
  await _loadRoboto();
  await _loadNovelSerif();
}

/// Material's icon font, which every `Icon` in the app draws from.
Future<void> _loadMaterialIcons() async {
  final path = _firstExisting(_sdkFontPaths(['MaterialIcons-Regular.otf']));
  if (path == null) {
    throw StateError(
      'MaterialIcons-Regular.otf not found — every Icon would render as a box. '
      'Run through `flutter test`, which sets FLUTTER_ROOT.',
    );
  }
  await _registerFamily('MaterialIcons', [path]);
}

/// Roboto, from the SDK's own cache, under every name the sans stack tries.
///
/// The app names its own families everywhere it styles text, but Material's
/// unstyled defaults and the novel reader's sans stack both end at the
/// platform face — which on Android is Roboto, and in `flutter_tester` is
/// nothing at all. Loading it keeps stray strings from rendering as boxes and
/// makes them render as what an Android reader actually sees.
Future<void> _loadRoboto() async {
  final paths = [
    for (final name in const [
      'Roboto-Regular.ttf',
      'Roboto-Medium.ttf',
      'Roboto-Bold.ttf',
    ])
      ...(_sdkFontPaths([name])),
  ].where((path) => File(path).existsSync()).toList();
  if (paths.isEmpty) return;
  for (final family in ['Roboto', ...kNovelSansStack]) {
    await _registerFamily(family, paths);
  }
}

/// A real serif for the novel surfaces.
///
/// `kNovelSerifStack` is deliberately system faces only — the app bundles no
/// webfont for prose — so in a test host, which has no system fonts at all,
/// every novel title and every line of a chapter renders as boxes. Registering
/// a serif under `Noto Serif`, the stack's Android entry, is what an Android
/// reader resolves to, so the shelf is captured in the face it actually wears.
Future<void> _loadNovelSerif() async {
  const candidates = [
    // Linux
    '/usr/share/fonts/noto/NotoSerif-Regular.ttf',
    '/usr/share/fonts/truetype/noto/NotoSerif-Regular.ttf',
    '/usr/share/fonts/liberation/LiberationSerif-Regular.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf',
    '/usr/share/fonts/TTF/DejaVuSerif.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf',
    // macOS
    '/System/Library/Fonts/Supplemental/Georgia.ttf',
    '/Library/Fonts/Georgia.ttf',
  ];
  final path = _firstExisting(candidates);
  if (path == null) {
    throw StateError(
      'No system serif found, so every novel title would render as a box. '
      'Install one of: $candidates',
    );
  }
  // Registered under *every* name in the stack, not just the Android one.
  // `flutter_tester` resolves an unknown family to its own box-drawing
  // placeholder rather than reporting a miss, so `fontFamilyFallback` is never
  // consulted: the stack's first entry, `Iowan Old Style`, "matches" the
  // placeholder and every novel title comes out as boxes. Registering the one
  // serif under all of them makes whichever name the engine reaches first
  // resolve to a real book face — which is what a device does too, just with
  // its own copy.
  for (final family in kNovelSerifStack) {
    await _registerFamily(family, [path]);
  }
}

Future<void> _registerFamily(String family, List<String> paths) async {
  final loader = FontLoader(family);
  for (final path in paths) {
    final bytes = File(path).readAsBytesSync();
    loader.addFont(Future.value(ByteData.view(bytes.buffer)));
  }
  await loader.load();
}

String? _firstExisting(Iterable<String> paths) {
  for (final path in paths) {
    if (File(path).existsSync()) return path;
  }
  return null;
}

/// Candidate locations for [names] inside the Flutter SDK's font cache.
Iterable<String> _sdkFontPaths(List<String> names) sync* {
  for (final root in _flutterRoots()) {
    for (final name in names) {
      yield '$root/bin/cache/artifacts/material_fonts/$name';
    }
  }
}

Iterable<String> _flutterRoots() sync* {
  final env = Platform.environment['FLUTTER_ROOT'];
  if (env != null && env.isNotEmpty) yield env;
  // `flutter test` sets FLUTTER_ROOT, but a bare `dart test` does not; the
  // resolved package config still points at the framework checkout.
  final config = File.fromUri(Uri.base.resolve('.dart_tool/package_config.json'));
  if (!config.existsSync()) return;
  final match = RegExp(r'"rootUri"\s*:\s*"([^"]*packages/flutter)"')
      .firstMatch(config.readAsStringSync());
  if (match == null) return;
  yield Uri.parse(match.group(1)!).toFilePath().replaceAll(
        RegExp(r'/packages/flutter/?$'),
        '',
      );
}

/// The phone these are shot on.
///
/// 412x915 is the common Android logical size, and Android is where most of
/// this app's readers are. It also clears the 400px rung in
/// `Responsive.seriesGridColumns`, so the poster grid is captured three
/// columns wide the way most readers actually see it, rather than the two a
/// narrower device falls back to.
///
/// 2x, not 3x: these are landing-page images. 3x produced a 1.2 MB PNG per
/// shot for detail no browser shows at the size the page paints them.
const Size kShotLogicalSize = Size(412, 915);
const double kShotPixelRatio = 2.0;

/// Sizes [tester]'s view to a phone and restores it afterwards.
void useShotViewport(WidgetTester tester) {
  tester.view.physicalSize = kShotLogicalSize * kShotPixelRatio;
  tester.view.devicePixelRatio = kShotPixelRatio;
  tester.view.padding = const FakeViewPadding(
    top: 59 * kShotPixelRatio,
    bottom: 34 * kShotPixelRatio,
  );
  addTearDown(tester.view.reset);
}

/// Advances the clock far enough for entrance animations to land.
///
/// `pumpAndSettle` is unusable here: the app shell paints a continuously
/// cross-fading mood backdrop and several looping shimmers, so "no frames
/// scheduled" never arrives and the settle spins until the suite times out.
/// Bounded pumps let the entrance animations finish and then stop.
Future<void> settleShot(WidgetTester tester) async {
  await tester.pump();
  for (final step in const [
    Duration(milliseconds: 350),
    Duration(milliseconds: 650),
    Duration(seconds: 1),
    Duration(seconds: 2),
  ]) {
    await tester.pump(step);
  }
}

/// Writes the widget under [finder] to [path] as a PNG.
///
/// The rasterisation and the file write both go through [WidgetTester.runAsync]
/// because both are real async work that `FakeAsync` would never complete.
Future<void> writeShot(
  WidgetTester tester,
  Finder finder,
  String path, {
  double pixelRatio = kShotPixelRatio,
}) async {
  final boundary = tester.renderObject<RenderRepaintBoundary>(finder);
  await tester.runAsync(() async {
    final image = await boundary.toImage(pixelRatio: pixelRatio);
    final data = await image.toByteData(format: ui.ImageByteFormat.png);
    image.dispose();
    final file = File(path);
    file.parent.createSync(recursive: true);
    file.writeAsBytesSync(data!.buffer.asUint8List());
  });
}

/// Where the served screenshots live — `SCREENSHOTS_DIR` in
/// `backend/routes/app_distribution.py`, mounted into the container by the
/// deploy.
const kShotOutputDir = 'docs/screenshots';

/// True when this run was asked to overwrite the committed screenshots.
bool get shotWritingEnabled =>
    (Platform.environment['MM_WRITE_SHOTS'] ?? '').trim().isNotEmpty;

/// Writes [name] into [kShotOutputDir], but only when `MM_WRITE_SHOTS` is set.
///
/// The capture itself runs either way: rasterising is most of the work and is
/// where a broken screen shows up, so an ordinary `flutter test` still proves
/// every screen in this file renders.
Future<void> maybeWriteShot(
  WidgetTester tester,
  Finder finder,
  String name,
) async {
  if (!shotWritingEnabled) {
    // Still rasterise, and throw away the bytes.
    final boundary = tester.renderObject<RenderRepaintBoundary>(finder);
    await tester.runAsync(() async {
      final image = await boundary.toImage(pixelRatio: kShotPixelRatio);
      image.dispose();
    });
    return;
  }
  await writeShot(tester, finder, '$kShotOutputDir/$name');
}

/// Fires `flutter_cache_manager`'s deferred cleanup timer.
///
/// The cache schedules a 10-second cleanup the first time it reads its
/// database. `AutomatedTestWidgetsFlutterBinding` fails any test that leaves a
/// timer pending at teardown, so the clock is advanced past it deliberately
/// rather than the invariant being suppressed.
Future<void> drainCacheTimers(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pump(const Duration(seconds: 11));
}
