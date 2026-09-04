import 'package:flutter/material.dart';

// The static `AppColors` table is gone: colours now come from the active
// palette via `context.colors.<token>` (see app_palette.dart /
// app_palettes.dart) so the whole app repaints when the theme switches.
// These exports keep the historical `import app_colors.dart` sites working.
export 'package:manhwamaniacs/app/theme/app_palette.dart';
export 'package:manhwamaniacs/app/theme/app_palettes.dart';

/// Muted, dark tints for reading-profile "moods" — the single source of truth
/// for mood hex on mobile (mirrors `frontend/src/features/profiles/mood.ts`).
///
/// Each hue is desaturated and dark on its own so that, blended at a low
/// ratio over the palette background, the result reads as a tinted surface
/// rather than a saturated colour. The tint dresses the profile picker and
/// the app-shell backdrop only — never the reader, which stays pure obsidian.
/// Widgets reference these tokens and blend them over `context.colors.bg`
/// (NOT a static base) so mood glows follow the active theme; they never
/// hard-code mood hex.
abstract final class ProfileMoodColors {
  /// The near-black anchor the tint hexes were designed over — the Eclipse
  /// background. Kept as the documented design reference; composite sites
  /// blend over the live `context.colors.bg` instead.
  static const Color base = Color(0xFF0A0A0A);

  static const Color romantic = Color(0xFF7C4A58); // dusty rose
  static const Color action = Color(0xFF6A2F33); // muted burgundy / red-brown
  static const Color comedy = Color(0xFF6F5228); // warm amber-brown
  static const Color horror = Color(0xFF3D3F57); // desaturated blue-gray
  static const Color sliceOfLife = Color(0xFF4C5C4F); // sage green-gray
  static const Color fantasy = Color(0xFF3F4D68); // deep teal-violet

  /// The untinted default — visually identical to the shell before profiles.
  static const Color neutral = base;
}
