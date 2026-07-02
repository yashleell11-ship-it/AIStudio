import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Reports whether the device is on an unmetered local connection.
abstract class NetworkConnectivity {
  Future<bool> isOnWifi();
}

class PlatformNetworkConnectivity implements NetworkConnectivity {
  PlatformNetworkConnectivity([Connectivity? connectivity])
      : _connectivity = connectivity ?? Connectivity();

  final Connectivity _connectivity;

  @override
  Future<bool> isOnWifi() async {
    final results = await _connectivity.checkConnectivity();
    return results.contains(ConnectivityResult.wifi) ||
        results.contains(ConnectivityResult.ethernet);
  }
}

final networkConnectivityProvider = Provider<NetworkConnectivity>(
  (_) => PlatformNetworkConnectivity(),
  name: 'networkConnectivity',
);
