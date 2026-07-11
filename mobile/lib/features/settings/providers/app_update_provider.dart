import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/settings/models/app_version.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:package_info_plus/package_info_plus.dart';

/// Checks the backend `/app/version` endpoint and returns update info.
/// Returns `null` if the check fails or the backend is unreachable.
final appUpdateProvider =
    FutureProvider.autoDispose<AppVersionInfo?>((ref) async {
  final dio = ref.watch(dioProvider);
  final baseUrl = ref.watch(apiBaseUrlProvider);

  final localInfo = await PackageInfo.fromPlatform();
  final localBuild = int.tryParse(localInfo.buildNumber) ?? 0;

  try {
    final response =
        await dio.get<Map<String, dynamic>>('/app/version');
    final data = response.data;
    if (data == null) return null;

    return AppVersionInfo.fromRemoteJson(
      data,
      localVersion: localInfo.version,
      localBuild: localBuild,
      apiBaseUrl: baseUrl,
    );
  } on DioException {
    return null;
  } catch (_) {
    return null;
  }
});
