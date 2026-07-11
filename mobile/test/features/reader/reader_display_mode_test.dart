import 'package:flutter_displaymode/flutter_displaymode.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/reader/utils/reader_display_mode.dart';
import 'package:manhwamaniacs/features/settings/models/reader_defaults.dart';

void main() {
  group('ReaderRefreshRate', () {
    test('maps each option to its target Hz (auto has none)', () {
      expect(ReaderRefreshRate.auto.targetHz, isNull);
      expect(ReaderRefreshRate.fps30.targetHz, 30);
      expect(ReaderRefreshRate.fps60.targetHz, 60);
      expect(ReaderRefreshRate.fps90.targetHz, 90);
      expect(ReaderRefreshRate.fps120.targetHz, 120);
    });

    test('fromStorageValue falls back to auto for unknown/null values', () {
      expect(ReaderRefreshRate.fromStorageValue(null), ReaderRefreshRate.auto);
      expect(
        ReaderRefreshRate.fromStorageValue('nonsense'),
        ReaderRefreshRate.auto,
      );
      expect(
        ReaderRefreshRate.fromStorageValue('fps120'),
        ReaderRefreshRate.fps120,
      );
    });
  });

  group('pickMode', () {
    // A phone panel offering 60/90/120 at one resolution, plus a stray mode at
    // a different resolution that must never be selected (it would relayout).
    const active =
        DisplayMode(id: 1, width: 1080, height: 2400, refreshRate: 120);
    const modes = <DisplayMode>[
      DisplayMode.auto, // id 0 — never a candidate
      DisplayMode(id: 1, width: 1080, height: 2400, refreshRate: 120),
      DisplayMode(id: 2, width: 1080, height: 2400, refreshRate: 90),
      DisplayMode(id: 3, width: 1080, height: 2400, refreshRate: 60),
      // different resolution — must never be selected
      DisplayMode(id: 4, width: 720, height: 1600, refreshRate: 60),
    ];

    test(
        'picks the mode closest to the requested rate at the active resolution',
        () {
      expect(pickMode(modes, active, 60)?.id, 3);
      expect(pickMode(modes, active, 90)?.id, 2);
      expect(pickMode(modes, active, 120)?.id, 1);
    });

    test('never selects a mode at a different resolution', () {
      // Ask for 60Hz: the 720x1600@60 entry matches exactly on rate but must
      // be rejected in favour of the same-resolution 60Hz mode.
      expect(pickMode(modes, active, 60)?.width, 1080);
    });

    test('rounds to the nearest available rate when exact match is absent', () {
      // 100Hz is between 90 and 120; nearest is 90 (id 2).
      expect(pickMode(modes, active, 100)?.id, 2);
      // 110Hz is closer to 120 (id 1).
      expect(pickMode(modes, active, 110)?.id, 1);
    });

    test('returns null when no concrete modes exist', () {
      expect(pickMode(const [DisplayMode.auto], active, 120), isNull);
    });
  });
}
