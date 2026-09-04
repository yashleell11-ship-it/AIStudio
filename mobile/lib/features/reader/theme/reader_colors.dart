import 'package:flutter/material.dart';

/// Reader-owned surface colours, deliberately NOT theme tokens.
///
/// The reader page surface is the reader's business: pages are pre-rendered
/// artwork, and the surface behind them (plus the loading/error states shown
/// *in place of* pages) must stay obsidian on every app theme so that
/// entering a chapter never flashes a light frame around dark artwork, and
/// the reader's own night overlays/dimming (warmth, brightness, background
/// setting) keep meaning. App themes style the reader CHROME (controls,
/// sheets, sliders) via `context.colors`; these constants style the pages.
abstract final class ReaderColors {
  /// The obsidian page backdrop (the pre-multi-theme app background).
  static const Color bg = Color(0xFF0A0A0A);

  /// Body text shown on [bg] (loading hints, page-error captions).
  static const Color fg = Color(0xFFDDE4EA);

  /// Secondary text shown on [bg].
  static const Color muted = Color(0xFF9AA8B4);

  /// Error tint shown on [bg].
  static const Color danger = Color(0xFFEF4444);
}
