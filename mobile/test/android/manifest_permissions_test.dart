import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Regression guard for the 1.2.3+6 login outage: the production/release APK
/// shipped with no `android.permission.INTERNET` because it was only declared
/// in the debug/profile source sets, which release builds do not merge. Every
/// request then failed with a generic connection error.
///
/// The merged manifest can't be asserted from a Dart unit test, so we pin the
/// source-of-truth main manifest instead. `flutter test` runs with the package
/// root as its working directory.
void main() {
  test('main AndroidManifest declares the INTERNET permission', () {
    final manifest = File('android/app/src/main/AndroidManifest.xml');
    expect(
      manifest.existsSync(),
      isTrue,
      reason: 'expected ${manifest.absolute.path} to exist',
    );

    final contents = manifest.readAsStringSync();
    expect(
      contents.contains(
        '<uses-permission android:name="android.permission.INTERNET" />',
      ),
      isTrue,
      reason:
          'Release APKs only merge main + plugin manifests, so INTERNET must '
          'be declared here or the app ships with no network access.',
    );
  });
}
