import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/reader/widgets/reader_content.dart';

void main() {
  group('autoScrollFrameDelta', () {
    test('advances speed/60 px on a 60 fps frame', () {
      expect(autoScrollFrameDelta(60, 1 / 60), closeTo(1.0, 1e-9));
      expect(autoScrollFrameDelta(30, 1 / 60), closeTo(0.5, 1e-9));
    });

    test('is frame-rate independent: same distance per second at any Hz', () {
      const speed = 90.0; // px per second
      double distanceOverOneSecond(int fps) {
        final dt = 1 / fps;
        var total = 0.0;
        for (var i = 0; i < fps; i++) {
          total += autoScrollFrameDelta(speed, dt);
        }
        return total;
      }

      // 60, 90 and 120 Hz panels all cover ~`speed` pixels in one second.
      expect(distanceOverOneSecond(60), closeTo(speed, 1e-6));
      expect(distanceOverOneSecond(90), closeTo(speed, 1e-6));
      expect(distanceOverOneSecond(120), closeTo(speed, 1e-6));
    });

    test('clamps an over-long frame (stall / resume) to one 60 fps step', () {
      // A 0.5s gap (backgrounded / GC) must not lurch forward by speed*0.5.
      expect(autoScrollFrameDelta(120, 0.5), closeTo(120 / 60, 1e-9));
    });

    test('ignores non-positive deltas', () {
      expect(autoScrollFrameDelta(120, 0), closeTo(120 / 60, 1e-9));
      expect(autoScrollFrameDelta(120, -0.01), closeTo(120 / 60, 1e-9));
    });
  });
}
