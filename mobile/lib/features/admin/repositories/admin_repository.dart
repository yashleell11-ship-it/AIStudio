import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/admin/models/account.dart';

/// Account administration. Every method is admin-only server-side and answers
/// 403 for anyone else, so callers gate on the current user before asking.
abstract class AdminRepository {
  /// Every account on this instance, newest signup last.
  Future<Result<List<Account>>> listAccounts();

  /// Enable or disable an account. Disabling ends its existing sessions at
  /// once rather than at token expiry, so the person is signed out on their
  /// next request rather than whenever their login happened to lapse.
  ///
  /// The server refuses this for the caller's own id.
  Future<Result<Account>> setActive({required int id, required bool active});

  /// Delete an account and everything it owns: profiles, follows, progress,
  /// sessions, bookmarks, tags, collections, notifications, reading stats.
  ///
  /// The server refuses this for the caller's own id.
  Future<Result<void>> deleteAccount(int id);
}
