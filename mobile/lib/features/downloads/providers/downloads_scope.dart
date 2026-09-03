import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/auth/models/auth_state.dart';
import 'package:manhwamaniacs/features/auth/providers/auth_controller.dart';
import 'package:manhwamaniacs/features/downloads/services/blob_store.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_db.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_store.dart';
import 'package:manhwamaniacs/features/profiles/providers/profiles_providers.dart';
import 'package:sqflite/sqflite.dart';

/// `"u{userId}p{profileId}"` — the leading column of every content primary
/// key in the on-device store. `null` when either half of the session is
/// missing, which is exactly when [downloadsStoreProvider] must hand back no
/// store at all.
String? downloadsScopeId({required int? userId, required int? profileId}) {
  if (userId == null || profileId == null) return null;
  return 'u${userId}p$profileId';
}

/// The current `(user, profile)` scope id, or `null` outside an active
/// session. Watching this — not [downloadsStoreProvider] directly — is
/// enough for UI that only needs to know *whether* a store exists.
final activeDownloadsScopeIdProvider = Provider<String?>(
  (ref) {
    final userId = ref.watch(
      authControllerProvider.select(
        (auth) => auth is AuthAuthenticated ? auth.user.id : null,
      ),
    );
    final profileId = ref.watch(activeProfileProvider.select((p) => p?.id));
    return downloadsScopeId(userId: userId, profileId: profileId);
  },
  name: 'activeDownloadsScopeId',
);

/// Generous upper bound for opening the local database/blob directory —
/// real disk I/O never approaches this. Its actual job is turning a wedged
/// platform channel (no native handler registered — every automated widget
/// test, and the one real-world case this could ever matter for: a corrupt
/// plugin registration) into a prompt, catchable failure instead of a hang
/// that never resolves. [DownloadsStore] callers already treat a failure
/// here as "store unavailable" (see `services/offline_reader.dart`'s
/// defensive catches), so timing out degrades exactly like any other
/// platform-channel error.
const _openTimeout = Duration(seconds: 3);

/// The single shared database backing every scope's `saved_chapters` /
/// `saved_pages` rows and the cross-scope `blobs` table. Opened once
/// (`keepAlive` — a `Provider`, not `autoDispose`) and reused for the life of
/// the app; switching profiles only changes which `scope_id` rows a
/// [DownloadsStore] built on top of it will read or write.
final downloadsDatabaseProvider = Provider<Future<Database>>(
  (ref) => openDownloadsDatabase().timeout(_openTimeout),
  name: 'downloadsDatabase',
);

/// The content-addressed blob tree under `Documents/mm-store/blobs` — shared
/// across scopes for cross-profile dedup, same reasoning as the database.
final blobStoreProvider = Provider<Future<BlobStore>>(
  (ref) => BlobStore.forApplicationDocuments().timeout(_openTimeout),
  name: 'blobStore',
);

/// The on-device chapter store for the active `(user, profile)` scope, or
/// `null` when no scope is resolvable — the structural half of isolation
/// (see [DownloadsStore]'s doc comment for the other half). Every screen that
/// reads or writes downloads must watch this, not construct a
/// [DownloadsStore] itself, so there is exactly one place scope resolution
/// can go wrong.
final downloadsStoreProvider = Provider<DownloadsStore?>(
  (ref) {
    final scopeId = ref.watch(activeDownloadsScopeIdProvider);
    if (scopeId == null) return null;
    return DownloadsStore(
      scopeId: scopeId,
      database: ref.watch(downloadsDatabaseProvider),
      blobStore: ref.watch(blobStoreProvider),
    );
  },
  name: 'downloadsStore',
);
