import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Impeller is Flutter's Android renderer by default (the tool's
/// `AndroidProject.computeImpellerEnabled` defaults to true and only an
/// `io.flutter.embedding.android.EnableImpeller` manifest entry can turn it
/// off). Nothing in this project switches it off, and nothing should: Skia's
/// runtime shader compilation is the classic source of first-scroll jank on
/// Android, which is exactly this app's complaint. This test exists so that
/// disabling it can only ever be a deliberate act with a failing test to
/// explain itself.
void main() {
  test('nothing disables Impeller on Android', () {
    final manifests = [
      'android/app/src/main/AndroidManifest.xml',
      'android/app/src/debug/AndroidManifest.xml',
      'android/app/src/profile/AndroidManifest.xml',
    ];

    for (final path in manifests) {
      final file = File(path);
      if (!file.existsSync()) continue;
      expect(
        file.readAsStringSync().contains('EnableImpeller'),
        isFalse,
        reason: '$path declares an Impeller override; the default (on) is '
            'what this app wants.',
      );
    }
  });
}
