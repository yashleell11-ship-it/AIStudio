import 'package:flutter/material.dart';

/// ManhwaManiacs "Eclipse Warm" color palette — dark-only.
///
/// Hex values mirror the web contract (frontend Eclipse Warm theme) exactly.
/// The historical token NAMES (violet*/cyan*) are preserved so every existing
/// screen adopts the warm amber/rose look without edits — only the VALUES moved.
abstract final class AppColors {
  // ── Backgrounds ────────────────────────────────────────────────────────────
  /// Main background (#0A0A0A) — near-black.
  static const Color bg = Color(0xFF0A0A0A);

  /// Abyss depth tone (#0A0A0A).
  static const Color abyss = Color(0xFF0A0A0A);

  /// Void surface (#111111).
  static const Color void_ = Color(0xFF111111);

  /// Panel / card background (#111111).
  static const Color panel = Color(0xFF111111);
  static const Color surface = panel;

  /// Secondary surface — lighter variant (#181818).
  static const Color surface2 = Color(0xFF181818);

  /// Sidebar background (#111111).
  static const Color sidebar = Color(0xFF111111);

  // ── Borders ────────────────────────────────────────────────────────────────
  /// Subtle border — rgba(221,228,234,0.12).
  static const Color border = Color(0x1FDDE4EA);

  // ── Foreground / Text ──────────────────────────────────────────────────────
  /// Primary text (#DDE4EA) — cool off-white.
  static const Color fg = Color(0xFFDDE4EA);

  /// Secondary / muted text (#9AA8B4).
  static const Color muted = Color(0xFF9AA8B4);

  // ── Primary brand (warm amber; NAME kept as violet*) ───────────────────────
  static const Color violet400 = Color(0xFFF6C177);

  /// Primary action color (#F59E0B) — warm amber.
  static const Color primary = Color(0xFFF59E0B);
  static const Color violet500 = primary;

  /// Primary hover / pressed state (#C2410C) — burnt orange.
  static const Color primaryHover = Color(0xFFC2410C);
  static const Color violet600 = primaryHover;

  static const Color primaryFg = Color(0xFF0C0C0C);

  // ── Accent (warm rose/ember; NAME kept as cyan*) ───────────────────────────
  static const Color cyan400 = Color(0xFFF6C177);

  /// Accent color (#BE4C00) — deep ember.
  static const Color accent = Color(0xFFBE4C00);
  static const Color cyan500 = accent;

  static const Color accentFg = Color(0xFFFFFFFF);

  // ── Semantic ───────────────────────────────────────────────────────────────
  static const Color danger = Color(0xFFEF4444);
  static const Color success = Color(0xFF10B981);
  static const Color warning = Color(0xFFF59E0B);

  // ── Extended accent palette ────────────────────────────────────────────────
  static const Color violet300 = Color(0xFFF6C177);
  static const Color amber400 = Color(0xFFFBBF24);
  static const Color emerald400 = Color(0xFF34d399);
  static const Color rose400 = Color(0xFFBE4C00);

  // ── Glass / Elevation ─────────────────────────────────────────────────────
  /// Top-edge highlight on glass cards — rgba(221,228,234,0.10).
  static const Color glassEdge = Color(0x1ADDE4EA);

  /// Surface elevated above panel — used for modal sheets, overlays (#181818).
  static const Color surfaceElevated = Color(0xFF181818);

  // ── Overlay / Scrim ───────────────────────────────────────────────────────
  static const Color scrim = Color(0xCC000000);

  /// Warm amber glow used for glassy effects.
  static const Color violetGlow = Color(0x33F59E0B);

  /// Warm ember glow for accent highlights.
  static const Color cyanGlow = Color(0x22BE4C00);

  // ── Eclipse Warm named tokens (new; used by page-level agents) ─────────────
  static const Color bgVoid = Color(0xFF0A0A0A);
  static const Color bgSurface = Color(0xFF111111);
  static const Color bgElevated = Color(0xFF181818);
  static const Color bgLight = Color(0xFFFFFFFF);
  static const Color textDark = Color(0xFF0C0C0C);
  static const Color accentAmber = Color(0xFFF59E0B);
  static const Color accentRose = Color(0xFFBE4C00);
  static const Color accentWarm = Color(0xFFC2410C);
  static const Color borderSubtle = Color(0x1FDDE4EA);
  static const Color borderLight = Color(0x1F0C0C0C);
}

/// Muted, dark tints for reading-profile "moods" — the single source of truth
/// for mood hex on mobile (mirrors `frontend/src/features/profiles/mood.ts`).
///
/// Each hue is desaturated and dark on its own so that, blended at a low ratio
/// over [AppColors.bg], the result reads as a tinted dark surface rather than a
/// saturated colour. The tint dresses the profile picker and the app-shell
/// backdrop only — never the reader, which stays pure obsidian. Widgets
/// reference these tokens; they never hard-code mood hex.
abstract final class ProfileMoodColors {
  /// The near-black base every tint is mixed over (== [AppColors.bg]).
  static const Color base = AppColors.bg;

  static const Color romantic = Color(0xFF7C4A58); // dusty rose
  static const Color action = Color(0xFF6A2F33); // muted burgundy / red-brown
  static const Color comedy = Color(0xFF6F5228); // warm amber-brown
  static const Color horror = Color(0xFF3D3F57); // desaturated blue-gray
  static const Color sliceOfLife = Color(0xFF4C5C4F); // sage green-gray
  static const Color fantasy = Color(0xFF3F4D68); // deep teal-violet

  /// The untinted default — visually identical to the shell before profiles.
  static const Color neutral = base;
}
