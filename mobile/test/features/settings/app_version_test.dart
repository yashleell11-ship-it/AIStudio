import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/settings/models/app_version.dart';

const _baseUrl = 'http://nas.local:8000';

AppVersionInfo _info({
  required AppUpdateChannel channel,
  int localBuild = 1,
  int remoteBuild = 2,
}) =>
    AppVersionInfo.fromRemoteJson(
      <String, dynamic>{'version': '1.3.3', 'build': remoteBuild},
      localVersion: '1.3.2',
      localBuild: localBuild,
      apiBaseUrl: _baseUrl,
      channel: channel,
    );

void main() {
  group('AppUpdateChannel.forPlatform', () {
    test('iOS is the SideStore channel', () {
      expect(
        AppUpdateChannel.forPlatform(TargetPlatform.iOS),
        AppUpdateChannel.sideStore,
      );
    });

    test('everything else is the APK channel', () {
      expect(
        AppUpdateChannel.forPlatform(TargetPlatform.android),
        AppUpdateChannel.apk,
      );
    });
  });

  group('AppVersionInfo download target', () {
    test('the APK channel points at the release APK', () {
      expect(
        _info(channel: AppUpdateChannel.apk).downloadUrl,
        '$_baseUrl/app/download',
      );
    });

    test('the SideStore channel points at the source manifest, never an .ipa',
        () {
      // /app/download serves application/vnd.android.package-archive, which an
      // iPhone cannot open. /app/ios/download serves a raw unsigned .ipa, which
      // is nearly as useless: only SideStore can sign it onto the device. The
      // manifest is the thing SideStore subscribes to.
      final url = _info(channel: AppUpdateChannel.sideStore).downloadUrl;
      expect(url, '$_baseUrl/app/source.json');
      expect(url, isNot(contains('/app/download')));
      expect(url, isNot(endsWith('.ipa')));
    });
  });

  group('AppVersionInfo.hasUpdate', () {
    test('a newer remote build is an update on the APK channel', () {
      expect(
        _info(channel: AppUpdateChannel.apk, localBuild: 17, remoteBuild: 18)
            .hasUpdate,
        isTrue,
      );
    });

    test('an equal or older remote build is not', () {
      expect(
        _info(channel: AppUpdateChannel.apk, localBuild: 18, remoteBuild: 18)
            .hasUpdate,
        isFalse,
      );
      expect(
        _info(channel: AppUpdateChannel.apk, localBuild: 19, remoteBuild: 18)
            .hasUpdate,
        isFalse,
      );
    });

    test('the SideStore channel never claims an update, in either direction',
        () {
      // /app/version reports the pubspec build — the Android channel's hand-set
      // counter. CI stamps iOS builds from a separate sequence (1000 + run
      // number), so the comparison is meaningless: it would offer an .apk to an
      // iPhone when the pubspec is bumped, and report "up to date" while
      // SideStore is sitting on a newer .ipa. Saying nothing is the honest
      // answer; SideStore owns the verdict.
      expect(
        _info(
          channel: AppUpdateChannel.sideStore,
          localBuild: 17,
          remoteBuild: 18,
        ).hasUpdate,
        isFalse,
      );
      expect(
        _info(
          channel: AppUpdateChannel.sideStore,
          localBuild: 1042,
          remoteBuild: 17,
        ).hasUpdate,
        isFalse,
      );
    });
  });
}
