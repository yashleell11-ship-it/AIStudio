import 'package:shared_preferences/shared_preferences.dart';

abstract final class _Keys {
  static const String readerMode = 'reader_mode';
  static const String readerBrightness = 'reader_brightness';
}

/// Light preferences that do not need encryption.
///
/// Used for UI settings (reader mode, brightness) that are non-sensitive
/// and acceptable in the platform's standard backup.
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
}
