import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/core/network/network_connectivity.dart';
import 'package:aistudio_mobile/features/downloads/utils/download_wifi_guard.dart';
import 'package:aistudio_mobile/features/settings/providers/settings_provider.dart';
import 'package:aistudio_mobile/shared/providers/core_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/test_overrides.dart';

class _FakeConnectivity implements NetworkConnectivity {
  _FakeConnectivity(this.onWifi);

  final bool onWifi;

  @override
  Future<bool> isOnWifi() async => onWifi;
}

void main() {
  group('download_wifi_guard', () {
    test('allows queue when Wi-Fi only is disabled', () async {
      SharedPreferences.setMockInitialValues(testPrefsDefaults());
      final prefs = await SharedPreferences.getInstance();
      final container = ProviderContainer(
        overrides: [
          sharedPrefsProvider.overrideWithValue(prefs),
          networkConnectivityProvider.overrideWithValue(_FakeConnectivity(false)),
        ],
      );
      addTearDown(container.dispose);

      expect(await checkWifiForDownload(container), isNull);
    });

    test('blocks queue on cellular when Wi-Fi only is enabled', () async {
      SharedPreferences.setMockInitialValues(
        testPrefsDefaults({'settings_wifi_only_downloads': true}),
      );
      final prefs = await SharedPreferences.getInstance();
      final container = ProviderContainer(
        overrides: [
          sharedPrefsProvider.overrideWithValue(prefs),
          networkConnectivityProvider.overrideWithValue(_FakeConnectivity(false)),
        ],
      );
      addTearDown(container.dispose);

      final error = await checkWifiForDownload(container);
      expect(isWifiRequiredDownloadError(error!), isTrue);
    });

    test('allows queue on Wi-Fi when Wi-Fi only is enabled', () async {
      SharedPreferences.setMockInitialValues(
        testPrefsDefaults({'settings_wifi_only_downloads': true}),
      );
      final prefs = await SharedPreferences.getInstance();
      final container = ProviderContainer(
        overrides: [
          sharedPrefsProvider.overrideWithValue(prefs),
          networkConnectivityProvider.overrideWithValue(_FakeConnectivity(true)),
        ],
      );
      addTearDown(container.dispose);

      expect(await checkWifiForDownload(container), isNull);
    });
  });
}
