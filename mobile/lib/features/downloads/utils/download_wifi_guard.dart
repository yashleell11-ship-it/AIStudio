import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/network/network_connectivity.dart';
import 'package:manhwamaniacs/features/settings/providers/settings_provider.dart';

const wifiRequiredDownloadError = ApiError(
  statusCode: 403,
  code: 'wifi_required',
  message:
      'Downloads are restricted to Wi-Fi. Connect to Wi-Fi or disable Wi-Fi only in Settings.',
);

bool isWifiRequiredDownloadError(AppError error) =>
    error is ApiError && error.code == 'wifi_required';

/// Blocks download queue requests when [wifiOnlyDownloadsProvider] is enabled
/// and the device is not on Wi-Fi.
Future<AppError?> checkWifiForDownload(Ref ref) async {
  if (!ref.read(wifiOnlyDownloadsProvider)) return null;

  final onWifi = await ref.read(networkConnectivityProvider).isOnWifi();
  if (onWifi) return null;

  return wifiRequiredDownloadError;
}
