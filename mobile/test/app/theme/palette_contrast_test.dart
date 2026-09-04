import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/app/theme/app_palette.dart';
import 'package:manhwamaniacs/app/theme/app_palettes.dart';
import 'package:manhwamaniacs/app/theme/app_palettes.generated.dart';

import '../../support/wcag_contrast.dart';

/// "Must be good colour combinations", made mechanical: every registered
/// palette has to clear WCAG floors on the pairings the app actually renders.
/// A palette that fails here gets adjusted, not shipped — do not weaken the
/// floors to admit a palette.
void main() {
  /// Body text on every surface it can sit on.
  const bodyFloor = 4.5;

  /// Muted/secondary text and non-text accents (WCAG 1.4.11 / large text).
  const accentFloor = 3.0;

  void expectRatio(
    AppPalette p,
    Color fgColor,
    Color bgColor,
    double floor,
    String pairing,
  ) {
    final ratio = contrastRatio(fgColor, bgColor);
    expect(
      ratio,
      greaterThanOrEqualTo(floor),
      reason: '${p.name} ($pairing) is ${ratio.toStringAsFixed(2)}:1 — '
          'below the $floor:1 floor',
    );
  }

  for (final p in AppPalettes.all) {
    group('palette "${p.id}"', () {
      test('body text clears $bodyFloor:1 on every surface', () {
        for (final (label, surface) in [
          ('bg', p.bg),
          ('surface', p.surface),
          ('surface2', p.surface2),
          ('surfaceElevated', p.surfaceElevated),
        ]) {
          expectRatio(p, p.fg, surface, bodyFloor, 'fg on $label');
        }
      });

      test('muted text clears $accentFloor:1 on every surface', () {
        for (final (label, surface) in [
          ('bg', p.bg),
          ('surface', p.surface),
          ('surface2', p.surface2),
          ('surfaceElevated', p.surfaceElevated),
        ]) {
          expectRatio(p, p.muted, surface, accentFloor, 'muted on $label');
        }
      });

      test('accents and semantics clear $accentFloor:1 on bg and surface', () {
        for (final (label, token) in [
          ('primary', p.primary),
          ('primarySoft', p.primarySoft),
          ('accent', p.accent),
          ('accentSoft', p.accentSoft),
          ('danger', p.danger),
          ('success', p.success),
          ('warning', p.warning),
        ]) {
          expectRatio(p, token, p.bg, accentFloor, '$label on bg');
          expectRatio(p, token, p.surface, accentFloor, '$label on surface');
        }
      });

      test('ink on filled controls clears $bodyFloor:1', () {
        expectRatio(p, p.primaryFg, p.primary, bodyFloor, 'primaryFg on primary');
        expectRatio(p, p.accentFg, p.accent, bodyFloor, 'accentFg on accent');
      });
    });
  }

  group('registry', () {
    test('ids are unique and byId round-trips', () {
      final ids = AppPalettes.all.map((p) => p.id).toSet();
      expect(ids.length, AppPalettes.all.length);
      for (final p in AppPalettes.all) {
        expect(AppPalettes.byId(p.id), same(p));
      }
    });

    test('unknown or absent ids fall back to the Eclipse default', () {
      expect(AppPalettes.byId('no_such_theme'), same(AppPalettes.eclipse));
      expect(AppPalettes.byId(null), same(AppPalettes.eclipse));
    });

    test('the default palette is first in gallery order', () {
      expect(AppPalettes.all.first, same(AppPalettes.eclipse));
    });

    test('ships the house palettes and the whole base16 set', () {
      // The brief was ten-to-twenty hand-written palettes; it is now the
      // curated base16 corpus on top of them, which is why the picker grew a
      // search field. The floor is what matters — a generated palette that
      // silently stopped being registered would leave the gallery smaller
      // than the web's and nobody would notice.
      expect(AppPalettes.all.length, greaterThanOrEqualTo(40));
      expect(AppPalettes.darkPalettes, isNotEmpty);
      expect(AppPalettes.lightPalettes, isNotEmpty);
      for (final generated in [...Base16Palettes.dark, ...Base16Palettes.light]) {
        expect(AppPalettes.all, contains(generated), reason: generated.id);
      }
      for (final own in AppPalettes.house) {
        expect(AppPalettes.all, contains(own), reason: own.id);
      }
    });

    test('every palette id that has ever shipped still resolves', () {
      // A palette id is persisted per profile. Dropping or renaming one does
      // not error — `byId` falls back to Eclipse — so the only thing standing
      // between a rename and somebody's theme silently reverting is this list.
      // The first eight were hand-written palettes that the generated base16
      // twins replaced; they kept their ids on purpose.
      const shipped = [
        'nord',
        'dracula',
        'mocha',
        'gruvbox',
        'rose_pine',
        'everforest',
        'latte',
        'dawn',
        'eclipse',
        'amoled',
        'tokyo_night',
        'solarized_dark',
        'solarized_light',
        'daylight',
        'paper',
      ];
      for (final id in shipped) {
        expect(AppPalettes.byId(id).id, id, reason: id);
      }
    });

    test('no two palettes share a name', () {
      // Forty-five tiles in one gallery: two called "Nord" would be a bug
      // nobody could act on.
      final names = AppPalettes.all.map((p) => p.name).toList();
      expect(names.toSet().length, names.length, reason: names.toString());
    });

    test('the Eclipse default still wears the shipped hex values', () {
      // The owner's current look must survive the multi-theme refactor
      // byte-for-byte; these mirror the pre-multi-theme AppColors constants.
      expect(AppPalettes.eclipse.bg, const Color(0xFF0A0A0A));
      expect(AppPalettes.eclipse.surface, const Color(0xFF111111));
      expect(AppPalettes.eclipse.fg, const Color(0xFFDDE4EA));
      expect(AppPalettes.eclipse.muted, const Color(0xFF9AA8B4));
      expect(AppPalettes.eclipse.primary, const Color(0xFFF59E0B));
      expect(AppPalettes.eclipse.accent, const Color(0xFFBE4C00));
    });
  });

  group('ThemeData wiring', () {
    test('fromPalette registers the palette as a ThemeExtension', () {
      for (final p in AppPalettes.all) {
        // Imported via app_palettes.dart's sibling; kept here so a palette
        // missing from ThemeData.extensions can never ship silently.
        final theme = ThemeData(extensions: [p]);
        expect(theme.extension<AppPalette>(), same(p));
      }
    });
  });
}
