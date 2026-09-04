import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/utils/responsive.dart';

void main() {
  group('gridTileWidth', () {
    test('divides the available width after the gutters are taken out', () {
      // 360 wide, 3 columns, two 12px gutters: 336 of covers over 3 tiles.
      expect(
        gridTileWidth(available: 360, columns: 3, spacing: 12),
        112,
      );
    });

    test('a single column is the whole width', () {
      expect(gridTileWidth(available: 360, columns: 1, spacing: 12), 360);
    });

    test('degrades to the available width rather than dividing by nothing', () {
      // Both of these are layout edge cases, not states a grid can be in; the
      // cover they feed asks for the original instead of NaN pixels.
      expect(gridTileWidth(available: 360, columns: 0, spacing: 12), 360);
      expect(
        gridTileWidth(available: double.infinity, columns: 3, spacing: 12),
        double.infinity,
      );
    });
  });
}
