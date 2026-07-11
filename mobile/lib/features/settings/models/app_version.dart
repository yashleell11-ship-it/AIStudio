class AppVersionInfo {
  const AppVersionInfo({
    required this.localVersion,
    required this.localBuild,
    required this.remoteVersion,
    required this.remoteBuild,
    required this.downloadUrl,
  });

  final String localVersion;
  final int localBuild;
  final String remoteVersion;
  final int remoteBuild;
  final String downloadUrl;

  bool get hasUpdate => remoteBuild > localBuild;

  factory AppVersionInfo.fromRemoteJson(
    Map<String, dynamic> json, {
    required String localVersion,
    required int localBuild,
    required String apiBaseUrl,
  }) {
    return AppVersionInfo(
      localVersion: localVersion,
      localBuild: localBuild,
      remoteVersion: json['version'] as String,
      remoteBuild: json['build'] as int,
      downloadUrl: '$apiBaseUrl/app/download',
    );
  }
}
