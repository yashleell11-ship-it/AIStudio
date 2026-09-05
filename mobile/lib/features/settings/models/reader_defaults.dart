// Default reading direction applied when a chapter is opened, until the
// user overrides it per-series (override logic is Reader-owned; this model
// only carries the persisted app-wide default).
import 'package:flutter/material.dart';

enum ReadingDirection {
  leftToRight,
  rightToLeft,
  vertical;

  bool get isVertical => this == ReadingDirection.vertical;

  bool get isHorizontal => !isVertical;

  Axis get scrollAxis => isVertical ? Axis.vertical : Axis.horizontal;

  bool get reverseScroll => this == ReadingDirection.rightToLeft;

  static ReadingDirection fromStorageValue(String? value) {
    return ReadingDirection.values.firstWhere(
      (mode) => mode.name == value,
      orElse: () => ReadingDirection.vertical,
    );
  }

  String get label => switch (this) {
        ReadingDirection.leftToRight => 'Left to right',
        ReadingDirection.rightToLeft => 'Right to left',
        ReadingDirection.vertical => 'Vertical',
      };
}

/// Default page fit mode applied in the reader.
enum ReaderFitMode {
  width,
  height,
  screen;

  static ReaderFitMode fromStorageValue(String? value) {
    return ReaderFitMode.values.firstWhere(
      (mode) => mode.name == value,
      orElse: () => ReaderFitMode.width,
    );
  }

  String get label => switch (this) {
        ReaderFitMode.width => 'Fit width',
        ReaderFitMode.height => 'Fit height',
        ReaderFitMode.screen => 'Fit screen',
      };
}

/// What one horizontal tap band does while the reader's chrome is hidden.
///
/// Same vocabulary as the web reader (`frontend/src/features/reader/keymap.ts`):
/// [advance] and [retreat] name the page-number direction, not a physical side,
/// so a configured zone means the same thing whichever way a series reads.
enum TapZoneAction {
  advance,
  retreat,
  toggle;

  String get label => switch (this) {
        TapZoneAction.advance => 'Next',
        TapZoneAction.retreat => 'Previous',
        TapZoneAction.toggle => 'Toggle',
      };
}

/// Left / centre / right tap behaviour.
///
/// Held as `null` on [ReaderDefaults] while the reader has never chosen one, so
/// the bands keep following [defaultFor] — including its right-to-left flip —
/// instead of freezing today's default into storage the first time the reader
/// is opened.
class TapZoneConfig {
  const TapZoneConfig({
    required this.left,
    required this.center,
    required this.right,
  });

  /// The behaviour before any customisation: the outer bands turn the page and
  /// the middle reveals the controls. Mirrored for a right-to-left series,
  /// where the next page is physically to the LEFT — the same flip the page
  /// list already applies via [ReadingDirection.reverseScroll].
  factory TapZoneConfig.defaultFor(ReadingDirection direction) => TapZoneConfig(
        left: direction.reverseScroll
            ? TapZoneAction.advance
            : TapZoneAction.retreat,
        center: TapZoneAction.toggle,
        right: direction.reverseScroll
            ? TapZoneAction.retreat
            : TapZoneAction.advance,
      );

  final TapZoneAction left;
  final TapZoneAction center;
  final TapZoneAction right;

  TapZoneConfig copyWith({
    TapZoneAction? left,
    TapZoneAction? center,
    TapZoneAction? right,
  }) =>
      TapZoneConfig(
        left: left ?? this.left,
        center: center ?? this.center,
        right: right ?? this.right,
      );

  /// One `left,center,right` string rather than three keys: a half-applied
  /// write would leave the reader with two zones doing the same thing and no
  /// way to tell that from a deliberate choice.
  String get storageValue => '${left.name},${center.name},${right.name}';

  /// `null` for absent or unreadable values — a blob that cannot be read whole
  /// is no opinion at all, so [defaultFor] keeps applying.
  static TapZoneConfig? fromStorageValue(String? value) {
    if (value == null) return null;
    final parts = value.split(',');
    if (parts.length != 3) return null;
    final actions = <TapZoneAction>[];
    for (final part in parts) {
      final matches = TapZoneAction.values.where((a) => a.name == part);
      if (matches.isEmpty) return null;
      actions.add(matches.first);
    }
    return TapZoneConfig(
      left: actions[0],
      center: actions[1],
      right: actions[2],
    );
  }
}

/// Preferred display refresh rate applied while the reader is open.
///
/// On Android this maps to a physical display mode via `flutter_displaymode`;
/// [auto] requests the highest rate the panel supports at the current
/// resolution. On platforms without switchable modes it is a no-op.
enum ReaderRefreshRate {
  auto,
  fps30,
  fps60,
  fps90,
  fps120;

  String get label => switch (this) {
        ReaderRefreshRate.auto => 'Auto',
        ReaderRefreshRate.fps30 => '30 FPS',
        ReaderRefreshRate.fps60 => '60 FPS',
        ReaderRefreshRate.fps90 => '90 FPS',
        ReaderRefreshRate.fps120 => '120 FPS',
      };

  /// Target refresh in Hz, or ``null`` for [auto] (use the highest available).
  double? get targetHz => switch (this) {
        ReaderRefreshRate.auto => null,
        ReaderRefreshRate.fps30 => 30,
        ReaderRefreshRate.fps60 => 60,
        ReaderRefreshRate.fps90 => 90,
        ReaderRefreshRate.fps120 => 120,
      };

  static ReaderRefreshRate fromStorageValue(String? value) {
    return ReaderRefreshRate.values.firstWhere(
      (rate) => rate.name == value,
      orElse: () => ReaderRefreshRate.auto,
    );
  }
}

/// App-wide default reader preferences, persisted via [PreferencesService]
/// and read by the Reader feature (not modified here).
class ReaderDefaults {
  const ReaderDefaults({
    required this.direction,
    required this.fitMode,
    required this.keepScreenAwake,
    required this.autoNextChapter,
    required this.lockControls,
    required this.refreshRate,
    required this.volumeKeyNavigation,
    this.tapZones,
  });

  final ReadingDirection direction;
  final ReaderFitMode fitMode;
  final bool keepScreenAwake;
  final bool autoNextChapter;
  final bool lockControls;
  final ReaderRefreshRate refreshRate;

  /// Page-turn on hardware volume keys (Android only; no-op elsewhere).
  final bool volumeKeyNavigation;

  /// Customised tap bands, or `null` for "follow the reading direction".
  final TapZoneConfig? tapZones;

  ReaderDefaults copyWith({
    ReadingDirection? direction,
    ReaderFitMode? fitMode,
    bool? keepScreenAwake,
    bool? autoNextChapter,
    bool? lockControls,
    ReaderRefreshRate? refreshRate,
    bool? volumeKeyNavigation,
    TapZoneConfig? tapZones,
    // An optional parameter cannot express "back to null", and null is the
    // meaningful "follow the reading direction" value for [tapZones].
    bool clearTapZones = false,
  }) =>
      ReaderDefaults(
        direction: direction ?? this.direction,
        fitMode: fitMode ?? this.fitMode,
        keepScreenAwake: keepScreenAwake ?? this.keepScreenAwake,
        autoNextChapter: autoNextChapter ?? this.autoNextChapter,
        lockControls: lockControls ?? this.lockControls,
        refreshRate: refreshRate ?? this.refreshRate,
        volumeKeyNavigation: volumeKeyNavigation ?? this.volumeKeyNavigation,
        tapZones: clearTapZones ? null : (tapZones ?? this.tapZones),
      );
}

/// Supported app languages. UI translation itself is not wired up (no
/// localization framework is present in this app yet) — selecting one only
/// persists the preference for the Reader/Library to pick up once
/// localization is added.
enum AppLanguage {
  english('en', 'English'),
  spanish('es', 'Español'),
  french('fr', 'Français'),
  german('de', 'Deutsch'),
  japanese('ja', '日本語'),
  korean('ko', '한국어');

  const AppLanguage(this.code, this.label);

  final String code;
  final String label;

  static AppLanguage fromCode(String? code) {
    return AppLanguage.values.firstWhere(
      (lang) => lang.code == code,
      orElse: () => AppLanguage.english,
    );
  }
}
