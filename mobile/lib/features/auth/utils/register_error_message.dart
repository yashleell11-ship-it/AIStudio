import 'package:manhwamaniacs/core/error/app_error.dart';

/// Maps a `/auth/register` failure to specific, actionable copy for the
/// registration screen.
///
/// [ApiError.userMessage] already surfaces whatever the backend sends, which
/// is fine for codes whose server-authored message is already the right
/// specific copy (`weak_password`, `invalid_username`) and for the transport
/// failure types ([NetworkError] / [TimeoutError] / ...). The codes called out
/// below get a client-authored message instead, so the important failures
/// read right even before/regardless of the exact backend copy:
///
///  - `invite_code_required` / `invite_code_invalid` — the invite-code gate.
///  - `registration_disabled` — self-service signup is off.
///  - `rate_limited` — the auth rate limiter tripped.
///  - `username_taken` — the one collision registration can hit.
String registerErrorMessage(AppError error) {
  if (error is ApiError) {
    switch (error.code) {
      case 'invite_code_required':
        return 'This server requires an invite code to create an account.';
      case 'invite_code_invalid':
        return "That invite code isn't valid — check it and try again.";
      case 'registration_disabled':
        return 'Registration is closed on this server.';
      case 'rate_limited':
        return 'Too many attempts — wait a moment and try again.';
      case 'username_taken':
        return 'That username is already taken.';
    }
  }
  return error.userMessage;
}
