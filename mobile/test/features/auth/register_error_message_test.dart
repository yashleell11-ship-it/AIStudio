import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/auth/utils/register_error_message.dart';

void main() {
  group('registerErrorMessage', () {
    test('invite_code_required gets specific copy', () {
      const error = ApiError(
        statusCode: 403,
        code: 'invite_code_required',
        message: 'server-authored message',
      );
      expect(
        registerErrorMessage(error),
        'This server requires an invite code to create an account.',
      );
    });

    test('invite_code_invalid gets specific copy, not the generic error', () {
      const error = ApiError(
        statusCode: 403,
        code: 'invite_code_invalid',
        message: 'server-authored message',
      );
      expect(
        registerErrorMessage(error),
        "That invite code isn't valid — check it and try again.",
      );
    });

    test('registration_disabled gets specific copy', () {
      const error = ApiError(
        statusCode: 403,
        code: 'registration_disabled',
        message: 'server-authored message',
      );
      expect(
        registerErrorMessage(error),
        'Registration is closed on this server.',
      );
    });

    test('rate_limited gets specific copy', () {
      const error = ApiError(
        statusCode: 429,
        code: 'rate_limited',
        message: 'Too many requests. Please slow down and try again shortly.',
      );
      expect(
        registerErrorMessage(error),
        'Too many attempts — wait a moment and try again.',
      );
    });

    test('username_taken gets specific copy', () {
      const error = ApiError(
        statusCode: 409,
        code: 'username_taken',
        message: 'server-authored message',
      );
      expect(
        registerErrorMessage(error),
        'That username is already taken.',
      );
    });

    test('unmapped ApiError codes fall back to the backend message', () {
      const error = ApiError(
        statusCode: 422,
        code: 'weak_password',
        message: 'Password is too common.',
      );
      expect(registerErrorMessage(error), 'Password is too common.');
    });

    test('non-ApiError failures fall back to userMessage', () {
      const error = NetworkError(message: 'blackholed', host: 'nas.local');
      expect(registerErrorMessage(error), error.userMessage);
    });
  });
}
