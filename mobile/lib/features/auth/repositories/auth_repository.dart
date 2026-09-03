import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/auth/models/auth_response.dart';
import 'package:manhwamaniacs/features/auth/models/auth_user.dart';
import 'package:manhwamaniacs/features/auth/models/bootstrap_status.dart';

/// Authentication API surface. Every method returns a [Result] so call sites
/// never handle raw `DioException`s.
abstract interface class AuthRepository {
  /// Public probe: whether the first admin still needs creating and whether
  /// registration is open. Never requires a token.
  Future<Result<BootstrapStatus>> bootstrapStatus();

  /// Log in with credentials. Bad credentials resolve to an `ApiError` (401).
  Future<Result<AuthResponse>> login({
    required String username,
    required String password,
    bool remember = true,
  });

  /// Create an account. The first account created on a fresh instance becomes
  /// the admin / owner.
  ///
  /// [inviteCode] is only sent when non-null/non-empty; the bootstrap account
  /// never needs one. A server that requires one and didn't get it, or got a
  /// wrong one, resolves to an `ApiError` (403, `invite_code_required` /
  /// `invite_code_invalid`).
  Future<Result<AuthResponse>> register({
    required String username,
    required String password,
    String? email,
    String? displayName,
    String? inviteCode,
    bool remember = true,
  });

  /// Revoke the current server-side session. The caller clears the local token
  /// regardless of the outcome.
  Future<Result<void>> logout();

  /// Resolve the current user from the active bearer token, or an `ApiError`
  /// (401) when the token is missing / expired.
  Future<Result<AuthUser>> me();
}
