import 'package:flutter/material.dart' show ThemeMode;
import 'package:shared_preferences/shared_preferences.dart';

abstract final class _Keys {
  static const String readerMode = 'reader_mode';
  static const String pinnedSources = 'pinned_sources';
  static const String readerBrightness = 'reader_brightness';
  static const String themeMode = 'settings_theme_mode';
  static const String language = 'settings_language';
  static const String readingDirection = 'settings_reading_direction';
  static const String readerFitMode = 'settings_reader_fit_mode';
  static const String keepScreenAwake = 'settings_keep_screen_awake';
  static const String autoNextChapter = 'settings_auto_next_chapter';
  static const String lockReaderControls = 'settings_lock_reader_controls';
  static const String readerRefreshRate = 'settings_reader_refresh_rate';
  static const String highRefreshRate = 'settings_high_refresh_rate';
  static const String readerWarmth = 'settings_reader_warmth';
  static const String readerBackground = 'settings_reader_background';
  static const String readerColorMode = 'settings_reader_color_mode';
  static const String libraryCoverScale = 'settings_library_cover_scale';
  static const String wifiOnlyDownloads = 'settings_wifi_only_downloads';
  static const String hapticFeedback = 'settings_haptic_feedback';
  static const String setupCompleted = 'settings_setup_completed';
  static const String lastSeenChangelogBuild = 'settings_last_seen_changelog_build';
  static const String volumeKeyNavigation = 'settings_volume_key_navigation';
  static const String readerTapZones = 'settings_reader_tap_zones';
  static const String cachedAuthUser = 'auth_cached_user';

  // On-device chapter store (1c-M3) — device properties, deliberately not
  // namespaced per profile: two profiles on one phone share one disk.
  static const String downloadStorageCap = 'settings_download_storage_cap';
  static const String downloadRetentionInterval =
      'settings_download_retention_interval';
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

  double get readerBrightness =>
      _prefs.getDouble(_Keys.readerBrightness) ?? 1.0;
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
  Future<void> setLanguage(String code) =>
      _prefs.setString(_Keys.language, code);

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

  bool get lockReaderControls =>
      _prefs.getBool(_Keys.lockReaderControls) ?? false;
  Future<void> setLockReaderControls(bool value) =>
      _prefs.setBool(_Keys.lockReaderControls, value);

  bool get volumeKeyNavigation =>
      _prefs.getBool(_Keys.volumeKeyNavigation) ?? false;
  Future<void> setVolumeKeyNavigation(bool value) =>
      _prefs.setBool(_Keys.volumeKeyNavigation, value);

  String? get readerRefreshRate => _prefs.getString(_Keys.readerRefreshRate);
  Future<void> setReaderRefreshRate(String value) =>
      _prefs.setString(_Keys.readerRefreshRate, value);

  /// Left/centre/right tap actions as a `TapZoneConfig` wire string (e.g.
  /// `'retreat,toggle,advance'`) — raw here so `core/` stays independent of
  /// `features/settings`, which owns the shape. Absent means the reader has
  /// never customised the bands and they follow the reading direction.
  String? get readerTapZones => _prefs.getString(_Keys.readerTapZones);
  Future<void> setReaderTapZones(String value) =>
      _prefs.setString(_Keys.readerTapZones, value);
  Future<void> clearReaderTapZones() => _prefs.remove(_Keys.readerTapZones);

  /// Run the whole app at the panel's fastest refresh rate (Android only).
  ///
  /// Defaults to **on**: every 90/120/144 Hz phone starts an app at 60 Hz
  /// unless it asks for more, and this app's core interaction is a continuous
  /// vertical scroll. Distinct from [readerRefreshRate], which is a per-chapter
  /// override — this one is app-wide and outlives the reader, so
  /// [resetReaderPreferences] deliberately leaves it alone.
  bool get highRefreshRate => _prefs.getBool(_Keys.highRefreshRate) ?? true;
  Future<void> setHighRefreshRate(bool value) =>
      _prefs.setBool(_Keys.highRefreshRate, value);

  double get readerWarmth => _prefs.getDouble(_Keys.readerWarmth) ?? 0.0;
  Future<void> setReaderWarmth(double value) =>
      _prefs.setDouble(_Keys.readerWarmth, value);

  String? get readerBackground => _prefs.getString(_Keys.readerBackground);
  Future<void> setReaderBackground(String value) =>
      _prefs.setString(_Keys.readerBackground, value);

  String? get readerColorMode => _prefs.getString(_Keys.readerColorMode);
  Future<void> setReaderColorMode(String value) =>
      _prefs.setString(_Keys.readerColorMode, value);

  double get libraryCoverScale =>
      _prefs.getDouble(_Keys.libraryCoverScale) ?? 1.0;
  Future<void> setLibraryCoverScale(double value) =>
      _prefs.setDouble(_Keys.libraryCoverScale, value);

  bool get wifiOnlyDownloads =>
      _prefs.getBool(_Keys.wifiOnlyDownloads) ?? false;
  Future<void> setWifiOnlyDownloads(bool value) =>
      _prefs.setBool(_Keys.wifiOnlyDownloads, value);

  bool get hapticFeedback => _prefs.getBool(_Keys.hapticFeedback) ?? true;
  Future<void> setHapticFeedback(bool value) =>
      _prefs.setBool(_Keys.hapticFeedback, value);

  bool get setupCompleted => _prefs.getBool(_Keys.setupCompleted) ?? false;
  Future<void> setSetupCompleted(bool value) =>
      _prefs.setBool(_Keys.setupCompleted, value);

  /// The app build number the user last saw the "What's new" sheet for.
  /// `0` means "never recorded" (fresh install) — distinct from having seen
  /// an actual build, so a brand-new install is never shown the sheet.
  int get lastSeenChangelogBuild =>
      _prefs.getInt(_Keys.lastSeenChangelogBuild) ?? 0;
  Future<void> setLastSeenChangelogBuild(int build) =>
      _prefs.setInt(_Keys.lastSeenChangelogBuild, build);

  /// The last user `/auth/me` confirmed, as its raw JSON blob (see
  /// `AuthUser.toJson`). Not a credential — the bearer token stays in secure
  /// storage — just enough identity to resolve a signed-in session when the
  /// server is unreachable at launch. Cleared whenever the session is.
  String? get cachedAuthUser => _prefs.getString(_Keys.cachedAuthUser);
  Future<void> setCachedAuthUser(String json) =>
      _prefs.setString(_Keys.cachedAuthUser, json);
  Future<void> clearCachedAuthUser() => _prefs.remove(_Keys.cachedAuthUser);

  /// The on-device downloads cap, as a [StorageCap] wire name (e.g. `'gb10'`)
  /// — raw string here so `core/` stays independent of `features/downloads`;
  /// `features/downloads` owns the enum and its default.
  String? get downloadStorageCap =>
      _prefs.getString(_Keys.downloadStorageCap);
  Future<void> setDownloadStorageCap(String value) =>
      _prefs.setString(_Keys.downloadStorageCap, value);

  /// The read-then-expire sweep interval, as a [RetentionInterval] wire name.
  String? get downloadRetentionInterval =>
      _prefs.getString(_Keys.downloadRetentionInterval);
  Future<void> setDownloadRetentionInterval(String value) =>
      _prefs.setString(_Keys.downloadRetentionInterval, value);

  List<String> get pinnedSources =>
      _prefs.getStringList(_Keys.pinnedSources) ?? [];
  Future<void> setPinnedSources(List<String> ids) =>
      _prefs.setStringList(_Keys.pinnedSources, ids);

  /// Clear every reader-related preference back to its built-in default.
  /// Deliberately leaves the server URL, setup flag, theme, language and
  /// pinned sources untouched so a reset never strands the user.
  Future<void> resetReaderPreferences() async {
    const keys = [
      _Keys.readerMode,
      _Keys.readerBrightness,
      _Keys.readerWarmth,
      _Keys.readerBackground,
      _Keys.readerColorMode,
      _Keys.readingDirection,
      _Keys.readerFitMode,
      _Keys.keepScreenAwake,
      _Keys.autoNextChapter,
      _Keys.lockReaderControls,
      _Keys.readerRefreshRate,
      _Keys.volumeKeyNavigation,
      _Keys.readerTapZones,
    ];
    for (final key in keys) {
      await _prefs.remove(key);
    }
  }
}
