import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/auth/models/auth_state.dart';
import 'package:manhwamaniacs/features/auth/models/auth_user.dart';
import 'package:manhwamaniacs/features/auth/providers/auth_controller.dart';
import 'package:manhwamaniacs/features/content_mode/content_mode.dart';
import 'package:manhwamaniacs/features/content_mode/content_mode_controller.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/providers/retention_maintenance_provider.dart';
import 'package:manhwamaniacs/features/downloads/services/blob_store.dart';
import 'package:manhwamaniacs/features/downloads/services/retention_maintenance.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_db.dart';
import 'package:manhwamaniacs/features/novels/providers/novels_gate_provider.dart';
import 'package:manhwamaniacs/features/profiles/models/mood.dart';
import 'package:manhwamaniacs/features/profiles/models/profile.dart';
import 'package:manhwamaniacs/features/profiles/providers/profiles_providers.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

/// Overrides [apiBaseUrlProvider] for widget/provider tests.
Override apiBaseUrlOverride(String url) =>
    apiBaseUrlProvider.overrideWith((ref) => url);

final _testUser = AuthUser(
  id: 1,
  username: 'tester',
  isAdmin: true,
  createdAt: DateTime.utc(2024),
);

/// Auth controller pre-seeded to an authenticated session — skips the launch
/// token restore and the network entirely.
class _AuthenticatedTestController extends AuthController {
  @override
  AuthState build() => AuthAuthenticated(_testUser);
}

/// Overrides the auth gate to an authenticated session so widget tests that
/// mount the full app land on the app shell instead of the login screen.
Override authenticatedAuthOverride() =>
    authControllerProvider.overrideWith(_AuthenticatedTestController.new);

/// Active reading profile pre-seeded so the post-auth profile gate lets the
/// full-app widget tests through to the shell instead of the profile picker.
class _SeededActiveProfileNotifier extends ActiveProfileNotifier {
  @override
  ActiveProfile? build() => const ActiveProfile(
        id: 1,
        name: 'Tester',
        avatarKey: null,
        mood: Mood.neutral,
      );
}

/// Overrides the active reading profile to a seeded persona so widget tests
/// that mount the full app pass the profile gate and land on the app shell.
Override activeProfileOverride() =>
    activeProfileProvider.overrideWith(_SeededActiveProfileNotifier.new);

/// Profile session pre-opened so the router's post-auth persona gate lets the
/// full-app widget tests straight through to the shell instead of parking on
/// the profile picker (which only opens once per app session).
class _ReadyProfileSessionNotifier extends ProfileSessionReadyNotifier {
  @override
  bool build() => true;
}

/// Overrides [profileSessionReadyProvider] so widget tests that mount the full
/// app skip the once-per-session profile picker and land on the app shell.
Override profileSessionReadyOverride() =>
    profileSessionReadyProvider.overrideWith(_ReadyProfileSessionNotifier.new);

/// Keeps the on-device chapter store entirely out of a full-app widget
/// test's way — otherwise:
///
/// - With [authenticatedAuthOverride] + [activeProfileOverride], any screen
///   the test mounts that touches the store (the reader, series detail,
///   Settings → Storage, …) resolves a *real* [DownloadsStore], reaching
///   real `sqflite`/`path_provider` platform channels with no native handler
///   registered in a widget-test host.
/// - `DownloadsLifecycleGate` (mounted unconditionally at the app root —
///   `app.dart`) runs its retention sweep on every launch/resume
///   *regardless* of auth state, via `retentionMaintenanceProvider`, which
///   is deliberately cross-scope and so isn't covered by overriding
///   [downloadsStoreProvider] alone.
///
/// Either path ends the same way: `downloads_scope.dart`'s defensive
/// `.timeout(...)` on the open call creates a real `Timer` to guard against
/// exactly this — an unresponsive platform channel — and a widget test
/// whose pump budget ends before that timeout elapses fails
/// `AutomatedTestWidgetsFlutterBinding`'s "no pending Timer after teardown"
/// invariant instead.
///
/// The fix is the same one `test/support/downloads_test_support.dart` uses
/// for the downloads feature's own tests: open a real (throwaway,
/// auto-deleted) SQLite database via `sqflite_common_ffi` instead of the
/// real plugin, so `downloadsDatabaseProvider`/`blobStoreProvider` resolve
/// almost instantly with no platform channel touched at all — an *empty*
/// store, not a *null* one for those two, since `RetentionMaintenance` (used
/// by `DownloadsLifecycleGate`'s launch/resume sweep regardless of auth
/// state) needs a real, queryable database rather than a value it would
/// have to special-case. [downloadsStoreProvider] itself is still forced to
/// `null`, which is the actual "no scope" isolation contract — every screen
/// this drives shows "nothing downloaded" from that, not from the
/// database being fake.
List<Override> noDownloadsStoreOverrides() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;
  final tempDir = Directory.systemTemp.createTempSync('mm-no-downloads-test-');
  final dbPath = '${tempDir.path}/downloads.db';
  final blobsDir = Directory('${tempDir.path}/blobs');

  Future<Database> openDb() => openDownloadsDatabase(overridePath: dbPath);
  Future<BlobStore> openBlobs() async => BlobStore(rootDirectory: blobsDir);

  return [
    downloadsStoreProvider.overrideWithValue(null),
    downloadsDatabaseProvider.overrideWith((ref) => openDb()),
    blobStoreProvider.overrideWith((ref) => openBlobs()),
    retentionMaintenanceProvider.overrideWith(
      (ref) => RetentionMaintenance(database: openDb(), blobStore: openBlobs()),
    ),
  ];
}

const setupCompletedPrefKey = 'settings_setup_completed';

/// Default prefs so tests skip the first-run setup redirect.
Map<String, Object> testPrefsDefaults([Map<String, Object> extra = const {}]) {
  return {
    setupCompletedPrefKey: true,
    ...extra,
  };
}


/// Content mode pinned, without SharedPreferences.
///
/// Every list in the app now asks which mode it is a list of, and the real
/// controller answers out of the per-profile preference store. A widget test
/// that only wants to render a screen should not have to seed that store, so
/// this pins the answer directly.
///
/// The defaults are the shipped deployment with the flag off: manga, no
/// switch, every filter a pass-through — which is exactly the app a test
/// written before novels existed expects to see.
class _FixedContentModeController extends ContentModeController {
  _FixedContentModeController(this._mode);

  final ContentMode _mode;

  @override
  ContentMode build() => _mode;
}

List<Override> contentModeOverrides({
  ContentMode mode = ContentMode.manga,
  bool novelsEnabled = false,
}) =>
    [
      novelsGateProvider.overrideWith((ref) async => novelsEnabled),
      novelsEnabledProvider.overrideWithValue(novelsEnabled),
      contentModeControllerProvider
          .overrideWith(() => _FixedContentModeController(mode)),
    ];
