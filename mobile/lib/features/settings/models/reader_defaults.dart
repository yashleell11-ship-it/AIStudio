/// Default reading direction applied when a chapter is opened, until the
/// user overrides it per-series (override logic is Reader-owned; this model
/// only carries the persisted app-wide default).
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

/// App-wide default reader preferences, persisted via [PreferencesService]
/// and read by the Reader feature (not modified here).
class ReaderDefaults {
  const ReaderDefaults({
    required this.direction,
    required this.fitMode,
    required this.keepScreenAwake,
    required this.autoNextChapter,
  });

  final ReadingDirection direction;
  final ReaderFitMode fitMode;
  final bool keepScreenAwake;
  final bool autoNextChapter;

  ReaderDefaults copyWith({
    ReadingDirection? direction,
    ReaderFitMode? fitMode,
    bool? keepScreenAwake,
    bool? autoNextChapter,
  }) =>
      ReaderDefaults(
        direction: direction ?? this.direction,
        fitMode: fitMode ?? this.fitMode,
        keepScreenAwake: keepScreenAwake ?? this.keepScreenAwake,
        autoNextChapter: autoNextChapter ?? this.autoNextChapter,
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
