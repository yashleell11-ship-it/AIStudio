import 'package:flutter/material.dart';

/// Reading-surface palettes for the novel reader — the same twelve the web
/// shipped, hex for hex (`frontend/src/features/novels/palettes.ts`).
///
/// The page a novel is read on is NOT the app's theme. A reader wants warm
/// paper at midday and a dim slate at 2am regardless of which of the fifteen
/// app themes the rest of the phone is wearing, and forcing the two to agree
/// is exactly the thing every dedicated reading app gets right. So the palette
/// is its own preference, and `"app"` — "Follow app theme" — is one option
/// among thirteen, not the frame the other twelve live inside.
///
/// ### Rules these colours obey, deliberately
///
/// - **No pure white on pure black.** Maximum-contrast text on an OLED-black
///   page haloes ("halation") and is genuinely painful over an hour. [black]
///   is `#000000` with a dimmed bone ink, never `#FFFFFF`.
/// - **Dark ink is dimmer than white on purpose.** Every dark palette's [ink]
///   sits well below 100% luminance. That is not an oversight to be "fixed".
/// - **Warm backgrounds get warm-dark ink**, never a neutral grey — neutral
///   grey over cream reads as dirty rather than soft.
///
/// ### Contrast floor
///
/// `test/features/novels/novel_palette_contrast_test.dart` asserts [ink]
/// clears **6:1** and [muted] clears **3:1** against [bg], the same way
/// `test/app/theme/palette_contrast_test.dart` does for the app themes. A
/// palette that misses that is a bug, not a matter of taste — long-form body
/// text is the one place in the app where a reader's eyes are on the same two
/// colours for an hour at a time.
///
/// Three of the approved colours missed that floor when the web measured them
/// and ship adjusted; those adjustments are carried across here verbatim
/// rather than re-derived, so the two clients cannot drift.
@immutable
class NovelPalette {
  const NovelPalette({
    required this.id,
    required this.label,
    required this.isDark,
    required this.bg,
    required this.ink,
    required this.muted,
  });

  final String id;
  final String label;

  /// Whether this is a light-on-dark surface — drives the status-bar icon
  /// brightness while the reader is fullscreen.
  final bool isDark;

  /// Page background.
  final Color bg;

  /// Body text.
  final Color ink;

  /// Chapter meta, dividers, the furniture around the prose.
  final Color muted;

  /// Hairlines and the quiet furniture: muted ink at 28%, well under it.
  Color get rule => muted.withValues(alpha: 0.28);
}

/// The palette registry, light surfaces first — the order the picker lists.
abstract final class NovelPalettes {
  // --- light surfaces ------------------------------------------------------

  static const paper = NovelPalette(
    id: 'paper',
    label: 'Paper',
    isDark: false,
    bg: Color(0xFFF5F1E8),
    ink: Color(0xFF2A2622),
    muted: Color(0xFF8A7F6D),
  );

  static const sepia = NovelPalette(
    id: 'sepia',
    label: 'Sepia',
    isDark: false,
    bg: Color(0xFFF4ECD8),
    ink: Color(0xFF5B4636),
    muted: Color(0xFF8A7250),
  );

  static const solarizedLight = NovelPalette(
    id: 'solarized-light',
    label: 'Solarized light',
    isDark: false,
    bg: Color(0xFFFDF6E3),
    // Approved as #586E75 (Solarized `base01`), which measures 4.99:1 here —
    // under the 6:1 floor. Darkened along its own hue to 6.50:1; visually the
    // same slate-teal, a shade deeper.
    ink: Color(0xFF4A5C62),
    // Approved as #93A1A1 (`base1`), 2.48:1 — under the 3:1 floor. Replaced
    // with Solarized's own `base00` (#657B83, 4.13:1): still canonical
    // Solarized, one step down the same ramp.
    muted: Color(0xFF657B83),
  );

  static const softGrey = NovelPalette(
    id: 'soft-grey',
    label: 'Soft grey',
    isDark: false,
    bg: Color(0xFFE9E9E7),
    ink: Color(0xFF2F2F2E),
    muted: Color(0xFF71716E),
  );

  static const cream = NovelPalette(
    id: 'cream',
    label: 'Cream',
    isDark: false,
    bg: Color(0xFFFBF7EF),
    ink: Color(0xFF33302B),
    muted: Color(0xFF8C857A),
  );

  static const dawn = NovelPalette(
    id: 'dawn',
    label: 'Dawn',
    isDark: false,
    bg: Color(0xFFFAF4ED),
    ink: Color(0xFF575279),
    // Approved as #9893A5 (Rosé Pine Dawn `muted`), 2.73:1 — under the 3:1
    // floor. Replaced with that theme's own `subtle` (#797593, 4.02:1), which
    // is the role Rosé Pine itself uses for secondary text.
    muted: Color(0xFF797593),
  );

  // --- dark surfaces -------------------------------------------------------

  static const dusk = NovelPalette(
    id: 'dusk',
    label: 'Dusk',
    isDark: true,
    bg: Color(0xFF1E1B18),
    ink: Color(0xFFD6D0C6),
    muted: Color(0xFF8A8078),
  );

  static const midnight = NovelPalette(
    id: 'midnight',
    label: 'Midnight',
    isDark: true,
    bg: Color(0xFF0F1419),
    ink: Color(0xFFC5CDD6),
    muted: Color(0xFF7B8794),
  );

  static const black = NovelPalette(
    id: 'black',
    label: 'True black',
    isDark: true,
    // Pure black background, deliberately NOT pure white ink — see the class
    // note on halation. This pairing is the whole reason that rule is written
    // down.
    bg: Color(0xFF000000),
    ink: Color(0xFFB8B5AF),
    muted: Color(0xFF6E6A64),
  );

  static const solarizedDark = NovelPalette(
    id: 'solarized-dark',
    label: 'Solarized dark',
    isDark: true,
    bg: Color(0xFF002B36),
    // Approved as #93A1A1 (`base1`), 5.61:1 — just under the 6:1 floor.
    // Lifted to 6.50:1. Solarized's own next step up is `base2` (#EEE8D5) at
    // 12.25:1, far too bright for a dark surface — see the "dark ink is
    // dimmer than white on purpose" rule.
    ink: Color(0xFFA1ADAD),
    muted: Color(0xFF657B83),
  );

  static const forest = NovelPalette(
    id: 'forest',
    label: 'Forest',
    isDark: true,
    bg: Color(0xFF1E2326),
    ink: Color(0xFFC5CDD0),
    muted: Color(0xFF7A8478),
  );

  static const rosePine = NovelPalette(
    id: 'rose-pine',
    label: 'Rosé Pine',
    isDark: true,
    bg: Color(0xFF191724),
    ink: Color(0xFFE0DEF4),
    muted: Color(0xFF908CAA),
  );

  static const List<NovelPalette> all = [
    paper,
    sepia,
    solarizedLight,
    softGrey,
    cream,
    dawn,
    dusk,
    midnight,
    black,
    solarizedDark,
    forest,
    rosePine,
  ];

  static List<NovelPalette> get lightPalettes =>
      all.where((p) => !p.isDark).toList();

  static List<NovelPalette> get darkPalettes =>
      all.where((p) => p.isDark).toList();

  /// The stored id meaning "Follow app theme" — paint with the app's own
  /// palette tokens instead of a reading surface of its own.
  static const String followAppId = 'app';

  /// The default surface for each scheme, when the reader has chosen nothing.
  static const NovelPalette defaultLight = paper;
  static const NovelPalette defaultDark = dusk;

  static bool isKnownId(String? id) =>
      id != null && all.any((p) => p.id == id);

  /// A stored id is a valid *choice* if it names a palette or asks to follow
  /// the app theme.
  static bool isChoice(String? id) => id == followAppId || isKnownId(id);

  /// The palette for [id], or `null` when [id] is unknown or [followAppId].
  ///
  /// `null` is a real answer, not a missing one: it means "inherit the app's
  /// tokens", which is what the reader renders when the owner picks
  /// "Follow app theme".
  static NovelPalette? byId(String? id) {
    for (final palette in all) {
      if (palette.id == id) return palette;
    }
    return null;
  }

  /// The choice actually in force.
  ///
  /// [stored] is whatever the profile picked, or `null` for "never chose one"
  /// — and only then does the app's own light/dark seed Paper or Dusk. An
  /// explicit choice is never overridden by a theme change: a reader on Sepia
  /// stays on Sepia when the app flips to dark, which is the entire point of
  /// the palette being independent.
  static String resolveChoice(String? stored, {required bool appIsDark}) {
    if (isChoice(stored)) return stored!;
    return (appIsDark ? defaultDark : defaultLight).id;
  }
}
