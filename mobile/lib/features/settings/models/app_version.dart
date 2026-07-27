import 'package:flutter/foundation.dart';

/// How this install receives updates.
///
/// The two channels do not share a build-number sequence and are not
/// interchangeable, which is why every update decision in the app has to know
/// which one it is on.
enum AppUpdateChannel {
  /// Android: the backend serves a release `.apk` that the user downloads and
  /// installs by hand. Build numbers come from `pubspec.yaml`, which is also
  /// what `/app/version` reports — so a remote-vs-local comparison is
  /// meaningful here.
  apk,

  /// iOS: sideloaded through SideStore on a free Apple ID. SideStore
  /// subscribes to the backend's AltStore source manifest and installs (and
  /// re-signs) on its own schedule; the app has nothing to hand the user.
  sideStore;

  static AppUpdateChannel forPlatform(TargetPlatform platform) =>
      platform == TargetPlatform.iOS
          ? AppUpdateChannel.sideStore
          : AppUpdateChannel.apk;
}

class AppVersionInfo {
  const AppVersionInfo({
    required this.localVersion,
    required this.localBuild,
    required this.remoteVersion,
    required this.remoteBuild,
    required this.downloadUrl,
    required this.channel,
  });

  final String localVersion;
  final int localBuild;
  final String remoteVersion;
  final int remoteBuild;

  /// Where the user is sent to get the newer build. Its meaning depends on
  /// [channel] — an installable artefact on [AppUpdateChannel.apk], a source
  /// manifest for SideStore to subscribe to on [AppUpdateChannel.sideStore].
  final String downloadUrl;

  final AppUpdateChannel channel;

  /// True only when this install can actually *act* on the difference.
  ///
  /// `/app/version` reports the `pubspec.yaml` build number — the Android
  /// channel's hand-set counter. iOS builds are stamped by CI from an entirely
  /// separate sequence, so comparing the two is meaningless in both
  /// directions: it either claims "up to date" while SideStore is sitting on a
  /// newer `.ipa`, or offers an Android `.apk` to a phone that cannot open it.
  /// On the SideStore channel the honest answer is to render no verdict and
  /// leave it to SideStore, which polls the manifest that does describe the
  /// published build.
  bool get hasUpdate =>
      channel == AppUpdateChannel.apk && remoteBuild > localBuild;

  factory AppVersionInfo.fromRemoteJson(
    Map<String, dynamic> json, {
    required String localVersion,
    required int localBuild,
    required String apiBaseUrl,
    required AppUpdateChannel channel,
  }) {
    return AppVersionInfo(
      localVersion: localVersion,
      localBuild: localBuild,
      remoteVersion: json['version'] as String,
      remoteBuild: json['build'] as int,
      channel: channel,
      downloadUrl: sourceUrlFor(channel, apiBaseUrl),
    );
  }

  /// The URL a given [channel] points at on a backend rooted at [apiBaseUrl].
  static String sourceUrlFor(AppUpdateChannel channel, String apiBaseUrl) =>
      switch (channel) {
        // Serves the release APK, `application/vnd.android.package-archive`.
        AppUpdateChannel.apk => '$apiBaseUrl/app/download',
        // The AltStore source manifest — deliberately not `/app/ios/download`.
        // A raw .ipa is nearly as useless as an .apk on a free Apple ID: only
        // SideStore can re-sign it onto the device, so the manifest (which
        // SideStore subscribes to) is the thing worth surfacing.
        AppUpdateChannel.sideStore => '$apiBaseUrl/app/source.json',
      };
}
