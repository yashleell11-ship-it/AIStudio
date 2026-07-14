/// Timing + phase map for the Netflix-style profile-selection takeover.
///
/// The whole ceremony is driven by a single [AnimationController] whose value
/// (0→1) is sliced into the phases below. Keeping the boundaries here — rather
/// than as scattered magic numbers in the widget — means the feel can be
/// retuned without touching layout code.
///
/// The [Interval]s are deliberately *linear* (no baked-in curve): they only
/// carve the timeline into phases. Each use-site applies its own easing so a
/// single phase can drive, say, an eased-out blur and an over-shooting scale
/// from the same fraction.
library;

import 'package:flutter/animation.dart';

/// Full ceremony length for the post-auth pick — the cinematic path the user
/// asked to last ~5 seconds.
const kProfileSelectionDuration = Duration(seconds: 5);

/// Compressed length when *switching* profiles from the in-app chip: the same
/// visual language, played as a brief full-screen flash.
const kProfileSwitchDuration = Duration(milliseconds: 250);

/// Phase boundaries as fractions of the controller's 0→1 timeline.
///
/// | phase      | window        | wall-clock (5s) | what moves                         |
/// |------------|---------------|-----------------|------------------------------------|
/// | [focus]    | 0.00 → 0.12   | 0 – 600ms       | others dim+blur, chosen tile scales, copy fades |
/// | [expand]   | 0.10 → 0.50   | 600ms – 2.5s    | mood floods from the tapped tile to full screen |
/// | [identity] | 0.42 → 0.72   | 2.1s – 3.6s     | centred avatar + name fade in over the flood    |
/// | [handoff]  | 0.90 → 1.00   | 4.5s – 5s       | flood settles onto the shell backdrop, identity fades |
abstract final class ProfileSelectPhases {
  const ProfileSelectPhases._();

  /// Focus: the non-selected tiles fall away while the chosen one lifts.
  static const Interval focus = Interval(0.0, 0.12);

  /// Expand: the mood colour blooms out to cover the viewport.
  static const Interval expand = Interval(0.10, 0.5);

  /// Identity: the "who's reading" avatar + name hold at centre.
  static const Interval identity = Interval(0.42, 0.72);

  /// Handoff: the flood eases onto the app-shell mood so home never pops.
  static const Interval handoff = Interval(0.9, 1.0);
}

/// Shared easing for the ceremony's use-sites. The [Interval]s above stay
/// deliberately *linear* — they only carve the timeline. These curves shape
/// *how* each phase spends its 0→1 fraction, so the feel can be retuned in one
/// place while the phase windows (and the timing contract the tests assert)
/// stay fixed.
abstract final class ProfileSelectCurves {
  const ProfileSelectCurves._();

  /// Cinematic ease for the mood bloom's growth, opacity fill and colour drift.
  static const Curve bloom = Curves.easeInOutCubic;

  /// The flood settling onto the shell backdrop during handoff.
  static const Curve settle = Curves.easeInOutCubic;

  /// Depth-of-field: the dim + gaussian blur landing on the non-chosen tiles.
  static const Curve focusFall = Curves.easeOutCubic;

  /// Gentle overshoot as the chosen tile lifts toward the viewer.
  static const Curve lift = Curves.easeOutBack;

  /// The centred avatar + name easing in (blur-in / scale-in / fade-up).
  static const Curve identityIn = Curves.easeOutCubic;

  /// The prompt copy dissolving as focus lands on the chosen profile.
  static const Curve copyFade = Curves.easeInOutCubic;
}
