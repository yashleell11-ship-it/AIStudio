import 'package:flutter/services.dart';

/// Centralised, tasteful haptic feedback.
///
/// Every reader gesture and key interaction routes through here so a single
/// user preference can mute all of them at once, and so each gesture maps to
/// the lightest platform primitive that fits it — feedback should feel like a
/// premium confirmation, never a buzzy annoyance.
///
/// Obtain an instance via `hapticsProvider` so the enabled flag stays in sync
/// with the user's setting.
class Haptics {
  const Haptics({required this.enabled});

  /// When ``false`` every method is a no-op.
  final bool enabled;

  /// Faintest tick — page turns, chip/toggle selection, moving between items.
  void selection() {
    if (!enabled) return;
    HapticFeedback.selectionClick();
  }

  /// Light tap — confirmations such as bookmarks, favouriting, opening a sheet.
  void light() {
    if (!enabled) return;
    HapticFeedback.lightImpact();
  }

  /// Firmer tap — reaching a boundary, chapter change, entering/leaving a mode.
  void medium() {
    if (!enabled) return;
    HapticFeedback.mediumImpact();
  }
}
