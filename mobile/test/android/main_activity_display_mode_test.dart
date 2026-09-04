import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// The window's `preferredDisplayModeId` is a single attribute with
/// last-writer-wins semantics, and the Kotlin that owns it cannot be reached
/// from a Dart test. So the source itself is pinned here, the same way
/// `manifest_permissions_test.dart` pins the manifest: these four properties
/// are the whole contract behind the "Smooth motion" setting, and each of them
/// has already been wrong once.
///
/// `flutter test` runs with the package root as its working directory.
void main() {
  late String source;

  setUpAll(() {
    final file = File(
      'android/app/src/main/kotlin/com/manhwamaniacs/reader/MainActivity.kt',
    );
    expect(
      file.existsSync(),
      isTrue,
      reason: 'expected ${file.absolute.path} to exist',
    );
    source = file.readAsStringSync();
  });

  test('the setting defaults to the panel maximum', () {
    expect(
      source.contains('private var highRefreshRateEnabled = true'),
      isTrue,
      reason: 'The native default must match '
          'PreferencesService.highRefreshRate so a cold start opens its first '
          'frames fast, before Dart has read the preference.',
    );
  });

  test('the toggle rides the existing native channel', () {
    expect(source.contains('"setHighRefreshRateEnabled" ->'), isTrue);
    expect(
      'com.manhwamaniacs.reader/native'.allMatches(source).length,
      1,
      reason: 'One MethodChannel for the native bridge, declared once.',
    );
  });

  test('turning it off clears the preference rather than stopping asking', () {
    expect(
      source.contains(
        'val target = if (highRefreshRateEnabled) '
        'fastestModeId() else SYSTEM_DEFAULT_MODE_ID',
      ),
      isTrue,
    );
    expect(source.contains('const val SYSTEM_DEFAULT_MODE_ID = 0'), isTrue);
  });

  test('the early return compares the preference, not the active mode', () {
    expect(
      source.contains(
        'if (window.attributes.preferredDisplayModeId == target) return',
      ),
      isTrue,
    );
    expect(
      source.contains('fastest.modeId == current.modeId'),
      isFalse,
      reason: 'Comparing the *active* mode returns early while the preference '
          'is still cleared — the panel is free to drop back a moment later '
          'with nothing to pull it up again.',
    );
  });
}
