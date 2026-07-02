import 'package:flutter/material.dart' show ThemeMode;
import 'package:shared_preferences/shared_preferences.dart';

abstract final class _Keys {
  static const String readerMode = 'reader_mode';
  static const String readerBrightness = 'reader_brightness';
  static const String themeMode = 'settings_theme_mode';
  static const String language = 'settings_language';
  static const String readingDirection = 'settings_reading_direction';
  static const String readerFitMode = 'settings_reader_fit_mode';
  static const String keepScreenAwake = 'settings_keep_screen_awake';
  static const String autoNextChapter = 'settings_auto_next_chapter';
  static const String wifiOnlyDownloads = 'settings_wifi_only_downloads';
  static const String setupCompleted = 'settings_setup_completed';
}

/// Light preferences that do not need encryption.
///
/// Used for UI settings (reader mode, brightness, theme, reader defaults,
/// download preferences) that are non-sensitive and acceptable in the
/// platform's standard backup. This is the single source of truth for all
/// locally-persisted app preferences — new settings should be added here
/// rather than introducing a second storage mechanism.
class PreferencesService {
  PreferencesService(this._prefs);

  final SharedPreferences _prefs;

  static Future<PreferencesService> create() async {
    final prefs = await SharedPreferences.getInstance();
    return PreferencesService(prefs);
  }

  String get readerMode => _prefs.getString(_Keys.readerMode) ?? 'paged';
  Future<void> setReaderMode(String mode) =>
      _prefs.setString(_Keys.readerMode, mode);

  double get readerBrightness => _prefs.getDouble(_Keys.readerBrightness) ?? 1.0;
  Future<void> setReaderBrightness(double value) =>
      _prefs.setDouble(_Keys.readerBrightness, value);

  ThemeMode get themeMode {
    switch (_prefs.getString(_Keys.themeMode)) {
      case 'light':
        return ThemeMode.light;
      case 'dark':
        return ThemeMode.dark;
      default:
        return ThemeMode.system;
    }
  }

  Future<void> setThemeMode(ThemeMode mode) =>
      _prefs.setString(_Keys.themeMode, mode.name);

  String get language => _prefs.getString(_Keys.language) ?? 'en';
  Future<void> setLanguage(String code) => _prefs.setString(_Keys.language, code);

  String? get readingDirection => _prefs.getString(_Keys.readingDirection);
  Future<void> setReadingDirection(String value) =>
      _prefs.setString(_Keys.readingDirection, value);

  String? get readerFitMode => _prefs.getString(_Keys.readerFitMode);
  Future<void> setReaderFitMode(String value) =>
      _prefs.setString(_Keys.readerFitMode, value);

  bool get keepScreenAwake => _prefs.getBool(_Keys.keepScreenAwake) ?? false;
  Future<void> setKeepScreenAwake(bool value) =>
      _prefs.setBool(_Keys.keepScreenAwake, value);

  bool get autoNextChapter => _prefs.getBool(_Keys.autoNextChapter) ?? true;
  Future<void> setAutoNextChapter(bool value) =>
      _prefs.setBool(_Keys.autoNextChapter, value);

  bool get wifiOnlyDownloads => _prefs.getBool(_Keys.wifiOnlyDownloads) ?? false;
  Future<void> setWifiOnlyDownloads(bool value) =>
      _prefs.setBool(_Keys.wifiOnlyDownloads, value);

  bool get setupCompleted => _prefs.getBool(_Keys.setupCompleted) ?? false;
  Future<void> setSetupCompleted(bool value) =>
      _prefs.setBool(_Keys.setupCompleted, value);
}
