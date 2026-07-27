import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Whether the current session is running on the cached identity because the
/// server could not be reached when it was restored.
///
/// Deliberately a separate flag rather than a fourth `AuthState` variant: the
/// router's switch over `AuthState` is exhaustive, so a new variant would force
/// an edit at every match site to express something only two screens care
/// about. It also lives in its own library so the profiles feature can read it
/// without importing the auth controller — which already imports the profile
/// providers, and would otherwise close an import cycle.
final sessionOfflineProvider = NotifierProvider<SessionOfflineNotifier, bool>(
  SessionOfflineNotifier.new,
  name: 'sessionOffline',
);

class SessionOfflineNotifier extends Notifier<bool> {
  @override
  bool build() => false;

  /// The session was resolved from cache — the server never answered.
  void markOffline() => state = true;

  /// The server answered (restore, login, register, or a 401), so whatever it
  /// said is authoritative and the session is no longer running blind.
  void markOnline() => state = false;
}
