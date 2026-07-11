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
  });

  final ReadingDirection direction;
  final ReaderFitMode fitMode;
  final bool keepScreenAwake;
  final bool autoNextChapter;
  final bool lockControls;
  final ReaderRefreshRate refreshRate;

  /// Page-turn on hardware volume keys (Android only; no-op elsewhere).
  final bool volumeKeyNavigation;

  ReaderDefaults copyWith({
    ReadingDirection? direction,
    ReaderFitMode? fitMode,
    bool? keepScreenAwake,
    bool? autoNextChapter,
    bool? lockControls,
    ReaderRefreshRate? refreshRate,
    bool? volumeKeyNavigation,
  }) =>
      ReaderDefaults(
        direction: direction ?? this.direction,
        fitMode: fitMode ?? this.fitMode,
        keepScreenAwake: keepScreenAwake ?? this.keepScreenAwake,
        autoNextChapter: autoNextChapter ?? this.autoNextChapter,
        lockControls: lockControls ?? this.lockControls,
        refreshRate: refreshRate ?? this.refreshRate,
        volumeKeyNavigation: volumeKeyNavigation ?? this.volumeKeyNavigation,
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
