import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

/// The system-UI mode the app rests in everywhere outside the reader.
///
/// Android keeps [SystemUiMode.immersiveSticky]: the navigation buttons
/// auto-hide and a swipe from the edge brings them back, which buys reading
/// area for free.
///
/// iOS must use [SystemUiMode.edgeToEdge]. The iOS embedder treats *every*
/// other mode as fullscreen — `FlutterPlatformPlugin` only leaves
/// `prefersStatusBarHidden` / `prefersHomeIndicatorAutoHidden` clear for
/// `edgeToEdge` — so `immersiveSticky` launches the app with no clock, battery
/// or signal for the whole session. Passing `overlays: [SystemUiOverlay.top]`
/// cannot rescue it either: `SystemChrome.setEnabledSystemUIMode` only forwards
/// that list when the mode is [SystemUiMode.manual] and silently drops it
/// otherwise.
SystemUiMode restingSystemUiMode(TargetPlatform platform) =>
    platform == TargetPlatform.iOS
        ? SystemUiMode.edgeToEdge
        : SystemUiMode.immersiveSticky;

/// The mode used while a chapter is open.
///
/// Fullscreen is wanted on both platforms here — the reader is the one screen
/// that deliberately gives up the status bar and the home indicator. Entry and
/// exit are symmetric: [applyReadingSystemUiMode] on mount,
/// [applyRestingSystemUiMode] on dispose, so leaving a chapter restores exactly
/// what the app launched with rather than permanently changing its shape.
const SystemUiMode readingSystemUiMode = SystemUiMode.immersiveSticky;

/// Applies [restingSystemUiMode] for the platform the app is running on.
Future<void> applyRestingSystemUiMode() => SystemChrome.setEnabledSystemUIMode(
      restingSystemUiMode(defaultTargetPlatform),
    );

/// Applies [readingSystemUiMode].
Future<void> applyReadingSystemUiMode() =>
    SystemChrome.setEnabledSystemUIMode(readingSystemUiMode);
