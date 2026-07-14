import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/features/profiles/models/mood.dart';

/// How strongly the mood tints the surface.
enum MoodBackdropVariant {
  /// Soft top-anchored glow for the app shell.
  shell,

  /// Slightly stronger glow for the full-bleed profile picker.
  picker,
}

/// Paints a muted, top-anchored radial glow of a profile [mood] over
/// [ProfileMoodColors.base] and cross-fades whenever the mood changes.
///
/// This is the SINGLE place the mood tint is composited — the reader is never
/// wrapped in it. The tint animates via an [AnimatedContainer]; the animation
/// collapses to an instant swap when the platform requests reduced motion
/// (`MediaQuery.disableAnimations`).
class MoodBackdrop extends StatelessWidget {
  const MoodBackdrop({
    super.key,
    required this.mood,
    required this.child,
    this.variant = MoodBackdropVariant.shell,
  });

  final Mood mood;
  final Widget child;
  final MoodBackdropVariant variant;

  static const Duration _crossFade = Duration(milliseconds: 420);

  double get _tintRatio => switch (variant) {
        MoodBackdropVariant.shell => 0.24,
        MoodBackdropVariant.picker => 0.34,
      };

  Alignment get _center => switch (variant) {
        MoodBackdropVariant.shell => const Alignment(0, -0.95),
        MoodBackdropVariant.picker => Alignment.topCenter,
      };

  double get _radius => switch (variant) {
        MoodBackdropVariant.shell => 1.25,
        MoodBackdropVariant.picker => 1.15,
      };

  double get _fade => switch (variant) {
        MoodBackdropVariant.shell => 0.62,
        MoodBackdropVariant.picker => 0.72,
      };

  @override
  Widget build(BuildContext context) {
    final reduceMotion = MediaQuery.disableAnimationsOf(context);
    final glow = mood.isTinted
        ? Color.lerp(ProfileMoodColors.base, mood.tint, _tintRatio)!
        : ProfileMoodColors.base;

    return AnimatedContainer(
      duration: reduceMotion ? Duration.zero : _crossFade,
      curve: Curves.easeOut,
      decoration: BoxDecoration(
        color: ProfileMoodColors.base,
        gradient: RadialGradient(
          center: _center,
          radius: _radius,
          colors: [glow, ProfileMoodColors.base],
          stops: [0.0, _fade],
        ),
      ),
      child: child,
    );
  }
}
