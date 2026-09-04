import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/novels/models/novel_palette.dart';

import '../../support/wcag_contrast.dart';

/// The reading palettes get the same mechanical treatment as the app themes
/// (`test/app/theme/palette_contrast_test.dart`) — with a HIGHER floor for
/// body text, because a reading surface is the one place in the app where the
/// owner's eyes are on the same two colours for an hour at a time.
///
/// A palette that fails here gets adjusted, not shipped. Do not weaken the
/// floors to admit a palette.
void main() {
  /// Body ink on the page. 6:1, well above the 4.5:1 the app themes hold to.
  const inkFloor = 6.0;

  /// Chapter meta, dividers, the furniture around the prose.
  const mutedFloor = 3.0;

  for (final palette in NovelPalettes.all) {
    group('novel palette "${palette.id}"', () {
      test('ink clears $inkFloor:1 on the page', () {
        final ratio = contrastRatio(palette.ink, palette.bg);
        expect(
          ratio,
          greaterThanOrEqualTo(inkFloor),
          reason: '${palette.label} ink is ${ratio.toStringAsFixed(2)}:1 — '
              'below the $inkFloor:1 floor',
        );
      });

      test('muted clears $mutedFloor:1 on the page', () {
        final ratio = contrastRatio(palette.muted, palette.bg);
        expect(
          ratio,
          greaterThanOrEqualTo(mutedFloor),
          reason: '${palette.label} muted is ${ratio.toStringAsFixed(2)}:1 — '
              'below the $mutedFloor:1 floor',
        );
      });
    });
  }

  group('halation rule', () {
    test('true black pairs pure black with a dimmed ink, never white', () {
      expect(NovelPalettes.black.bg.toARGB32(), 0xFF000000);
      // The rule this palette exists to prove: maximum-contrast white on an
      // OLED-black page haloes and is painful over an hour.
      expect(NovelPalettes.black.ink.toARGB32(), isNot(0xFFFFFFFF));
      expect(
        contrastRatio(NovelPalettes.black.ink, NovelPalettes.black.bg),
        lessThan(15),
      );
    });

    test('every dark palette keeps its ink below white', () {
      for (final palette in NovelPalettes.darkPalettes) {
        expect(
          relativeLuminance(palette.ink),
          lessThan(1.0),
          reason: '${palette.label} ink is at full luminance',
        );
      }
    });
  });

  group('registry', () {
    test('ships the same twelve surfaces the web does', () {
      expect(NovelPalettes.all, hasLength(12));
      expect(NovelPalettes.lightPalettes, hasLength(6));
      expect(NovelPalettes.darkPalettes, hasLength(6));
    });

    test('ids are unique and byId round-trips', () {
      final ids = NovelPalettes.all.map((p) => p.id).toSet();
      expect(ids.length, NovelPalettes.all.length);
      for (final palette in NovelPalettes.all) {
        expect(NovelPalettes.byId(palette.id), same(palette));
      }
    });

    test('the two defaults wear the hexes the web shipped', () {
      expect(NovelPalettes.defaultLight.id, 'paper');
      expect(NovelPalettes.paper.bg.toARGB32(), 0xFFF5F1E8);
      expect(NovelPalettes.paper.ink.toARGB32(), 0xFF2A2622);
      expect(NovelPalettes.defaultDark.id, 'dusk');
      expect(NovelPalettes.dusk.bg.toARGB32(), 0xFF1E1B18);
      expect(NovelPalettes.dusk.ink.toARGB32(), 0xFFD6D0C6);
    });

    test('"follow app theme" is a choice but not a palette', () {
      expect(NovelPalettes.isChoice(NovelPalettes.followAppId), isTrue);
      expect(NovelPalettes.isKnownId(NovelPalettes.followAppId), isFalse);
      expect(NovelPalettes.byId(NovelPalettes.followAppId), isNull);
    });

    test('an unstored choice is seeded by the app theme, once', () {
      expect(NovelPalettes.resolveChoice(null, appIsDark: false), 'paper');
      expect(NovelPalettes.resolveChoice(null, appIsDark: true), 'dusk');
      // An explicit choice is never overridden by a theme flip — that is the
      // entire point of the palette being independent.
      expect(NovelPalettes.resolveChoice('sepia', appIsDark: true), 'sepia');
      expect(
        NovelPalettes.resolveChoice(NovelPalettes.followAppId, appIsDark: false),
        NovelPalettes.followAppId,
      );
      // Garbage in storage falls back rather than throwing.
      expect(NovelPalettes.resolveChoice('no-such-palette', appIsDark: true), 'dusk');
    });
  });
}
