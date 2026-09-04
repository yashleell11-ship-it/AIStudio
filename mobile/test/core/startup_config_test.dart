import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/config/startup_config.dart';
import 'package:manhwamaniacs/core/storage/preferences.dart';
import 'package:manhwamaniacs/core/storage/secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _prodUrl = 'https://app.manhwamaniacs.xyz';

void main() {
  group('resolveStartupConfig', () {
    test('baked prod build ignores stale localhost override', () {
      final config = resolveStartupConfig(
        savedUrl: 'http://127.0.0.1:8000',
        setupCompleted: true,
        hasBakedProductionUrl: true,
        defaultApiUrl: _prodUrl,
      );

      expect(config.apiUrl, _prodUrl);
      expect(config.persistApiUrl, _prodUrl);
      expect(config.markSetupCompleted, isFalse);
    });

    test('baked prod build migrates wrong https host', () {
      final config = resolveStartupConfig(
        savedUrl: 'https://manhwamaniacs.xyz',
        setupCompleted: true,
        hasBakedProductionUrl: true,
        defaultApiUrl: _prodUrl,
      );

      expect(config.apiUrl, _prodUrl);
      expect(config.persistApiUrl, _prodUrl);
    });

    test('baked prod build skips write when storage already matches', () {
      final config = resolveStartupConfig(
        savedUrl: _prodUrl,
        setupCompleted: true,
        hasBakedProductionUrl: true,
        defaultApiUrl: _prodUrl,
      );

      expect(config.apiUrl, _prodUrl);
      expect(config.persistApiUrl, isNull);
      expect(config.markSetupCompleted, isFalse);
    });

    test('baked prod build marks setup complete on first launch', () {
      final config = resolveStartupConfig(
        savedUrl: null,
        setupCompleted: false,
        hasBakedProductionUrl: true,
        defaultApiUrl: _prodUrl,
      );

      expect(config.apiUrl, _prodUrl);
      expect(config.persistApiUrl, _prodUrl);
      expect(config.markSetupCompleted, isTrue);
    });

    test('dev build keeps saved URL override', () {
      const saved = 'http://192.168.0.10:8000';
      final config = resolveStartupConfig(
        savedUrl: saved,
        setupCompleted: true,
        hasBakedProductionUrl: false,
        defaultApiUrl: 'http://127.0.0.1:8000',
      );

      expect(config.apiUrl, saved);
      expect(config.persistApiUrl, isNull);
      expect(config.markSetupCompleted, isFalse);
    });

    test('dev build uses compile-time default when storage is empty', () {
      const defaultUrl = 'http://127.0.0.1:8000';
      final config = resolveStartupConfig(
        savedUrl: null,
        setupCompleted: false,
        hasBakedProductionUrl: false,
        defaultApiUrl: defaultUrl,
      );

      expect(config.apiUrl, defaultUrl);
      expect(config.persistApiUrl, isNull);
      expect(config.markSetupCompleted, isFalse);
    });
  });

  group('applyStartupConfig', () {
    test('persists baked prod URL and marks setup complete', () async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();
      final storage = _FakeSecureStorageService(storedUrl: 'http://127.0.0.1:8000');

      final apiUrl = await applyStartupConfig(
        storage: storage,
        preferences: PreferencesService(prefs),
        hasBakedProductionUrl: true,
        defaultApiUrl: _prodUrl,
      );

      expect(apiUrl, _prodUrl);
      expect(storage.storedUrl, _prodUrl);
      expect(PreferencesService(prefs).setupCompleted, isTrue);
    });

    test('leaves dev override untouched', () async {
      SharedPreferences.setMockInitialValues({'settings_setup_completed': true});
      final prefs = await SharedPreferences.getInstance();
      const saved = 'http://192.168.0.10:8000';
      final storage = _FakeSecureStorageService(storedUrl: saved);

      final apiUrl = await applyStartupConfig(
        storage: storage,
        preferences: PreferencesService(prefs),
        hasBakedProductionUrl: false,
      );

      expect(apiUrl, saved);
      expect(storage.storedUrl, saved);
    });

    test('uses a savedUrl the caller already has in flight', () async {
      SharedPreferences.setMockInitialValues({'settings_setup_completed': true});
      final prefs = await SharedPreferences.getInstance();
      const inFlight = 'http://192.168.0.50:8000';
      final storage = _FakeSecureStorageService(storedUrl: 'http://10.0.0.1:8000');

      final apiUrl = await applyStartupConfig(
        storage: storage,
        preferences: PreferencesService(prefs),
        hasBakedProductionUrl: false,
        savedUrl: Future<String?>.value(inFlight),
      );

      expect(apiUrl, inFlight);
      // The point of the parameter: `main` starts the Keystore read alongside
      // the SharedPreferences load, so this must not read it a second time.
      expect(storage.getApiUrlCalls, 0);
    });
  });
}

class _FakeSecureStorageService extends SecureStorageService {
  _FakeSecureStorageService({this.storedUrl});

  String? storedUrl;
  int getApiUrlCalls = 0;

  @override
  Future<String?> getApiUrl() async {
    getApiUrlCalls++;
    return storedUrl;
  }

  @override
  Future<void> setApiUrl(String url) async {
    storedUrl = url;
  }
}
