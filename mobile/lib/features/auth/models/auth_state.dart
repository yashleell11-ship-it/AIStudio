import 'package:manhwamaniacs/features/auth/models/auth_user.dart';

/// The app-wide authentication status.
///
/// [AuthUnknown] is the transient cold-start state while a stored token is
/// validated against `/auth/me`; the router shows a splash for it and does not
/// bounce the user to login until the status resolves.
sealed class AuthState {
  const AuthState();

  bool get isAuthenticated => this is AuthAuthenticated;
}

/// Cold start: a stored session is still being restored / validated.
final class AuthUnknown extends AuthState {
  const AuthUnknown();
}

/// No valid session — the user must log in or register.
final class AuthUnauthenticated extends AuthState {
  const AuthUnauthenticated();
}

/// A valid session is active for [user].
final class AuthAuthenticated extends AuthState {
  const AuthAuthenticated(this.user);

  final AuthUser user;
}
