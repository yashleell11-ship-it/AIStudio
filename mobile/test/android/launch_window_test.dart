import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// The app never follows the OS light/dark setting — `app.dart` hands the same
/// ThemeData to `theme:` and `darkTheme:` because the in-app gallery owns the
/// choice — so the Android launch window must not follow it either. On the
/// stock Flutter template `values/styles.xml` inherited `Theme.Light`, and a
/// phone in system Light mode showed a full white window for the whole
/// pre-first-frame duration before snapping to the near-black app.
void main() {
  test('the light-mode launch window is as dark as the night one', () {
    final day = File('android/app/src/main/res/values/styles.xml');
    final night = File('android/app/src/main/res/values-night/styles.xml');
    expect(day.existsSync(), isTrue, reason: day.absolute.path);
    expect(night.existsSync(), isTrue, reason: night.absolute.path);

    final dayXml = day.readAsStringSync();
    expect(dayXml.contains('@android:style/Theme.Light'), isFalse);
    expect(
      '@android:style/Theme.Black.NoTitleBar'.allMatches(dayXml).length,
      2,
      reason: 'Both LaunchTheme and NormalTheme paint before/behind the '
          'Flutter UI.',
    );
  });

  test('no launch drawable paints white', () {
    for (final path in const [
      'android/app/src/main/res/drawable/launch_background.xml',
      'android/app/src/main/res/drawable-v21/launch_background.xml',
    ]) {
      final file = File(path);
      expect(file.existsSync(), isTrue, reason: file.absolute.path);
      expect(
        file.readAsStringSync().contains('@android:color/white'),
        isFalse,
        reason: '$path still paints the stock template white.',
      );
    }
  });
}
