import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';

/// The reading-profile "moods" the backend accepts for `profiles.mood`.
///
/// Kept in lockstep with the backend `Mood` literal and the web
/// `frontend/src/features/profiles/mood.ts`. Each mood carries a muted, dark
/// tint (see [ProfileMoodColors]) that dresses the picker and the app shell.
enum Mood {
  romantic,
  action,
  comedy,
  horror,
  sliceOfLife,
  fantasy,
  neutral;

  /// The wire value sent to / received from the backend (`snake_case`, with
  /// [Mood.neutral] serialised as `"default"`).
  String get wire => switch (this) {
        Mood.sliceOfLife => 'slice_of_life',
        Mood.neutral => 'default',
        _ => name,
      };

  /// Human-readable label for the picker and the editor form.
  String get label => switch (this) {
        Mood.romantic => 'Romantic',
        Mood.action => 'Action',
        Mood.comedy => 'Comedy',
        Mood.horror => 'Horror',
        Mood.sliceOfLife => 'Slice of Life',
        Mood.fantasy => 'Fantasy',
        Mood.neutral => 'Default',
      };

  /// The muted tint for this mood, mixed over [ProfileMoodColors.base] by the
  /// backdrop. No mood hex ever lives outside [ProfileMoodColors].
  Color get tint => switch (this) {
        Mood.romantic => ProfileMoodColors.romantic,
        Mood.action => ProfileMoodColors.action,
        Mood.comedy => ProfileMoodColors.comedy,
        Mood.horror => ProfileMoodColors.horror,
        Mood.sliceOfLife => ProfileMoodColors.sliceOfLife,
        Mood.fantasy => ProfileMoodColors.fantasy,
        Mood.neutral => ProfileMoodColors.neutral,
      };

  /// True when the mood actually tints the surface (everything but the default).
  bool get isTinted => this != Mood.neutral;

  /// Narrow an arbitrary wire value to a [Mood], defaulting to [Mood.neutral].
  static Mood fromWire(String? value) {
    for (final mood in Mood.values) {
      if (mood.wire == value) return mood;
    }
    return Mood.neutral;
  }
}
