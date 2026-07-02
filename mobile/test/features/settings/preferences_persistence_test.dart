import 'package:aistudio_mobile/core/storage/preferences.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

Future<PreferencesService> _freshService() async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();
  return PreferencesService(prefs);
}

void main() {
  group('PreferencesService theme persistence', () {
    test('defaults to ThemeMode.system when nothing is saved', () async {
      final service = await _freshService();
      expect(service.themeMode, ThemeMode.system);
    });

    test('round-trips each ThemeMode value through storage', () async {
      final service = await _freshService();

      for (final mode in ThemeMode.values) {
        await service.setThemeMode(mode);
        expect(service.themeMode, mode);
      }
    });

    test('persists across a new PreferencesService instance over the same prefs',
        () async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();
      final first = PreferencesService(prefs);
      await first.setThemeMode(ThemeMode.dark);

      final second = PreferencesService(prefs);
      expect(second.themeMode, ThemeMode.dark);
    });
  });

  group('PreferencesService language persistence', () {
    test('defaults to "en"', () async {
      final service = await _freshService();
      expect(service.language, 'en');
    });

    test('round-trips a language code', () async {
      final service = await _freshService();
      await service.setLanguage('ja');
      expect(service.language, 'ja');
    });
  });

  group('PreferencesService reader default preferences persistence', () {
    test('reading direction, fit mode, keep-awake, and auto-next round-trip', () async {
      final service = await _freshService();

      expect(service.readingDirection, isNull);
      expect(service.readerFitMode, isNull);
      expect(service.keepScreenAwake, isFalse);
      expect(service.autoNextChapter, isTrue);

      await service.setReadingDirection('rightToLeft');
      await service.setReaderFitMode('height');
      await service.setKeepScreenAwake(true);
      await service.setAutoNextChapter(false);

      expect(service.readingDirection, 'rightToLeft');
      expect(service.readerFitMode, 'height');
      expect(service.keepScreenAwake, isTrue);
      expect(service.autoNextChapter, isFalse);
    });
  });

  group('PreferencesService download preferences persistence', () {
    test('wifiOnlyDownloads defaults to false and round-trips', () async {
      final service = await _freshService();
      expect(service.wifiOnlyDownloads, isFalse);

      await service.setWifiOnlyDownloads(true);
      expect(service.wifiOnlyDownloads, isTrue);

      await service.setWifiOnlyDownloads(false);
      expect(service.wifiOnlyDownloads, isFalse);
    });
  });

  group('PreferencesService pre-existing reader settings are untouched', () {
    test('readerMode and readerBrightness keep their original defaults', () async {
      final service = await _freshService();
      expect(service.readerMode, 'paged');
      expect(service.readerBrightness, 1.0);
    });
  });
}
