import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/auth/utils/session_device_label.dart';

/// The sessions list exists to answer one question — "is one of these not
/// me?" — and it can only answer it if the labels are distinguishable. These
/// pin the cases where a naive `contains` gets that wrong: every Chromium
/// agent claims to be Safari, and every iOS agent claims to be a Mac.
void main() {
  group('sessionDeviceLabel', () {
    test('the phone client is named as the app, not as dart:io', () {
      expect(sessionDeviceLabel('Dart/3.5 (dart:io)'), 'ManhwaManiacs app');
    });

    test('a browser is named with the platform it ran on', () {
      expect(
        sessionDeviceLabel(
          'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        ),
        'Chrome on Windows',
      );
    });

    test('Edge is not reported as Chrome', () {
      expect(
        sessionDeviceLabel(
          'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 Edg/128.0.0.0',
        ),
        'Edge on Windows',
      );
    });

    test('an iPhone is not reported as a Mac', () {
      expect(
        sessionDeviceLabel(
          'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
          'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 '
          'Mobile/15E148 Safari/604.1',
        ),
        'Safari on iPhone',
      );
    });

    test('Firefox on Android keeps both halves', () {
      expect(
        sessionDeviceLabel(
          'Mozilla/5.0 (Android 14; Mobile; rv:128.0) Gecko/128.0 Firefox/128.0',
        ),
        'Firefox on Android',
      );
    });

    test('a session with no agent at all still names itself', () {
      expect(sessionDeviceLabel(null), 'Unknown device');
      expect(sessionDeviceLabel('   '), 'Unknown device');
    });

    // The row worth reading is the one nothing recognises, so an unknown agent
    // keeps its own text rather than being flattened to "Unknown device".
    test('an unrecognised agent keeps its identifying text', () {
      expect(sessionDeviceLabel('curl/8.4.0'), 'curl/8.4.0');
    });

    test('and is truncated rather than allowed to run off the row', () {
      final label = sessionDeviceLabel('x' * 120);
      expect(label.length, 40);
      expect(label.endsWith('…'), isTrue);
    });
  });
}
