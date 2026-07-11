import 'package:flutter/material.dart';

/// ManhwaManiacs v2 color palette — dark-only.
///
/// All hex values are taken directly from frontend/src/app/globals.css @theme.
abstract final class AppColors {
  // ── Backgrounds ────────────────────────────────────────────────────────────
  /// Main background (#030507) — almost black.
  static const Color bg = Color(0xFF030507);

  /// Slightly lighter depth tone (#080c10).
  static const Color abyss = Color(0xFF080c10);

  /// Void surface (#0d1117).
  static const Color void_ = Color(0xFF0d1117);

  /// Panel / card background (#111820).
  static const Color panel = Color(0xFF111820);
  static const Color surface = panel;

  /// Secondary surface — lighter variant (#1a2332).
  static const Color surface2 = Color(0xFF1a2332);

  /// Sidebar background (#0f1419).
  static const Color sidebar = Color(0xFF0f1419);

  // ── Borders ────────────────────────────────────────────────────────────────
  /// Subtle border (#1e293b).
  static const Color border = Color(0xFF1e293b);

  // ── Foreground / Text ──────────────────────────────────────────────────────
  /// Primary text (#f1f5f9) — light gray.
  static const Color fg = Color(0xFFf1f5f9);

  /// Secondary / muted text (#64748b).
  static const Color muted = Color(0xFF64748b);

  // ── Primary brand (Violet) ─────────────────────────────────────────────────
  static const Color violet400 = Color(0xFFa78bfa);

  /// Primary action color (#8b5cf6) — violet-500.
  static const Color primary = Color(0xFF8b5cf6);
  static const Color violet500 = primary;

  /// Primary hover / pressed state (#7c3aed) — violet-600.
  static const Color primaryHover = Color(0xFF7c3aed);
  static const Color violet600 = primaryHover;

  static const Color primaryFg = Color(0xFFffffff);

  // ── Accent (Cyan) ──────────────────────────────────────────────────────────
  static const Color cyan400 = Color(0xFF22d3ee);

  /// Accent color (#06b6d4) — cyan-500.
  static const Color accent = Color(0xFF06b6d4);
  static const Color cyan500 = accent;

  static const Color accentFg = Color(0xFFffffff);

  // ── Semantic ───────────────────────────────────────────────────────────────
  static const Color danger = Color(0xFFef4444);
  static const Color success = Color(0xFF10b981);
  static const Color warning = Color(0xFFf59e0b);

  // ── Extended accent palette ────────────────────────────────────────────────
  static const Color violet300 = Color(0xFFc4b5fd);
  static const Color amber400 = Color(0xFFfbbf24);
  static const Color emerald400 = Color(0xFF34d399);
  static const Color rose400 = Color(0xFFfb7185);

  // ── Glass / Elevation ─────────────────────────────────────────────────────
  /// Top-edge highlight on glass cards (simulates light reflection).
  static const Color glassEdge = Color(0xFF26334a);

  /// Surface elevated above panel — used for modal sheets, overlays.
  static const Color surfaceElevated = Color(0xFF1d2b3a);

  // ── Overlay / Scrim ───────────────────────────────────────────────────────
  static const Color scrim = Color(0xCC000000);

  /// Violet glow used for glassy effects — matches CSS `--shadow-glow`.
  static const Color violetGlow = Color(0x338b5cf6);

  /// Cyan glow for accent highlights.
  static const Color cyanGlow = Color(0x2206b6d4);
}
