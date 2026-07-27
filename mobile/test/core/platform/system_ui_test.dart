import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/platform/system_ui.dart';

void main() {
  group('restingSystemUiMode', () {
    test('iOS gets edgeToEdge so the status bar survives launch', () {
      // Every mode except edgeToEdge is fullscreen to the iOS embedder: it sets
      // both prefersStatusBarHidden and prefersHomeIndicatorAutoHidden. Asking
      // for immersiveSticky here launched the app with no clock, battery or
      // signal for the whole session.
      expect(
        restingSystemUiMode(TargetPlatform.iOS),
        SystemUiMode.edgeToEdge,
      );
    });

    test('Android keeps the auto-hiding nav buttons', () {
      expect(
        restingSystemUiMode(TargetPlatform.android),
        SystemUiMode.immersiveSticky,
      );
    });

    test('the reader is fullscreen on every platform', () {
      expect(readingSystemUiMode, SystemUiMode.immersiveSticky);
    });

    test('entering and leaving the reader is symmetric on iOS', () {
      // The reader hides the status bar and dispose restores exactly what the
      // app launched with. Previously dispose hardcoded edgeToEdge, which on
      // iOS was the *only* call that ever un-hid the bar — so the app silently
      // changed shape the first time a chapter was closed and never changed
      // back.
      expect(
        readingSystemUiMode,
        isNot(restingSystemUiMode(TargetPlatform.iOS)),
        reason: 'the reader must actually change something on iOS',
      );
      expect(
        restingSystemUiMode(TargetPlatform.iOS),
        SystemUiMode.edgeToEdge,
        reason: 'and leaving must land back on the launch mode',
      );
    });
  });
}
