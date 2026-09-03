import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/network/interceptors/error_interceptor.dart';
import 'package:manhwamaniacs/features/auth/models/bootstrap_status.dart';
import 'package:manhwamaniacs/features/auth/repositories/auth_repository_impl.dart';
import 'package:mocktail/mocktail.dart';

/// Exercises [AuthRepositoryImpl] against a mocked [HttpClientAdapter] rather
/// than a hand-written fake, so the exact wire contract — the JSON body posted
/// to `/auth/register` and the [ApiError] produced from a given status/body —
/// is verified for real, through Dio's actual request/response pipeline (with
/// the same [ErrorInterceptor] the production client installs).
///
/// The invite-code contract this targets is a *design*, not yet landed on the
/// backend as of writing (`backend/routes/auth.py` has no `invite_code`
/// handling) — see the mobile agent's report for what was verified against
/// landed code vs. design. These tests document exactly what the client sends
/// and how it interprets each response, so they will need a look once the
/// backend lands and the shapes can be checked against control.
class _MockHttpClientAdapter extends Mock implements HttpClientAdapter {}

class _FakeRequestOptions extends Fake implements RequestOptions {}

ResponseBody _jsonBody(Map<String, dynamic> body, int statusCode) {
  return ResponseBody.fromString(
    jsonEncode(body),
    statusCode,
    headers: {
      Headers.contentTypeHeader: [Headers.jsonContentType],
    },
  );
}

Map<String, dynamic> _userJson() => {
      'id': 1,
      'username': 'newuser',
      'email': null,
      'display_name': null,
      'is_admin': false,
      'created_at': '2026-01-01T00:00:00Z',
      'last_login_at': null,
    };

void main() {
  setUpAll(() {
    registerFallbackValue(_FakeRequestOptions());
  });

  late _MockHttpClientAdapter adapter;
  late Dio dio;
  late AuthRepositoryImpl repository;

  setUp(() {
    adapter = _MockHttpClientAdapter();
    dio = Dio(BaseOptions(baseUrl: 'https://mm.test'))
      ..httpClientAdapter = adapter
      // Matches production wiring (`createDioClient`) for the piece under
      // test: DioException -> AppError mapping.
      ..interceptors.add(ErrorInterceptor());
    repository = AuthRepositoryImpl(dio);
  });

  group('register request body', () {
    test('omits invite_code when none is given', () async {
      RequestOptions? captured;
      when(() => adapter.fetch(any(), any(), any())).thenAnswer((inv) async {
        captured = inv.positionalArguments[0] as RequestOptions;
        return _jsonBody({'user': _userJson(), 'token': 'tok'}, 201);
      });

      final result = await repository.register(
        username: 'newuser',
        password: 'password1',
      );

      expect(result.isOk, isTrue);
      final body = captured!.data as Map<String, dynamic>;
      expect(body.containsKey('invite_code'), isFalse);
    });

    test('includes invite_code when one is given', () async {
      RequestOptions? captured;
      when(() => adapter.fetch(any(), any(), any())).thenAnswer((inv) async {
        captured = inv.positionalArguments[0] as RequestOptions;
        return _jsonBody({'user': _userJson(), 'token': 'tok'}, 201);
      });

      final result = await repository.register(
        username: 'newuser',
        password: 'password1',
        inviteCode: 'HOUSEHOLD-42',
      );

      expect(result.isOk, isTrue);
      final body = captured!.data as Map<String, dynamic>;
      expect(body['invite_code'], 'HOUSEHOLD-42');
    });

    test('an empty invite_code is treated the same as none', () async {
      RequestOptions? captured;
      when(() => adapter.fetch(any(), any(), any())).thenAnswer((inv) async {
        captured = inv.positionalArguments[0] as RequestOptions;
        return _jsonBody({'user': _userJson(), 'token': 'tok'}, 201);
      });

      await repository.register(
        username: 'newuser',
        password: 'password1',
        inviteCode: '',
      );

      final body = captured!.data as Map<String, dynamic>;
      expect(body.containsKey('invite_code'), isFalse);
    });
  });

  group('register error mapping', () {
    Future<AppError> errorFor(int statusCode, String code, String message) async {
      when(() => adapter.fetch(any(), any(), any())).thenAnswer(
        (_) async => _jsonBody({'code': code, 'message': message}, statusCode),
      );
      final result = await repository.register(
        username: 'newuser',
        password: 'password1',
      );
      expect(result.isErr, isTrue);
      return result.error;
    }

    test('403 invite_code_required maps to an ApiError with that code',
        () async {
      final error = await errorFor(
        403,
        'invite_code_required',
        'An invite code is required.',
      );
      expect(error, isA<ApiError>());
      final apiError = error as ApiError;
      expect(apiError.statusCode, 403);
      expect(apiError.code, 'invite_code_required');
    });

    test('403 invite_code_invalid maps to an ApiError with that code',
        () async {
      final error = await errorFor(
        403,
        'invite_code_invalid',
        'That invite code is invalid.',
      );
      expect(error, isA<ApiError>());
      expect((error as ApiError).code, 'invite_code_invalid');
    });

    test('403 registration_disabled maps to an ApiError with that code',
        () async {
      final error = await errorFor(
        403,
        'registration_disabled',
        'Registration is disabled.',
      );
      expect(error, isA<ApiError>());
      expect((error as ApiError).code, 'registration_disabled');
    });

    test('429 rate_limited maps to an ApiError with that status/code',
        () async {
      final error = await errorFor(
        429,
        'rate_limited',
        'Too many requests. Please slow down and try again shortly.',
      );
      expect(error, isA<ApiError>());
      final apiError = error as ApiError;
      expect(apiError.statusCode, 429);
      expect(apiError.code, 'rate_limited');
    });

    test('409 username_taken maps to an ApiError with that status/code',
        () async {
      final error = await errorFor(
        409,
        'username_taken',
        'That username is already taken.',
      );
      expect(error, isA<ApiError>());
      final apiError = error as ApiError;
      expect(apiError.statusCode, 409);
      expect(apiError.code, 'username_taken');
    });
  });

  group('bootstrapStatus', () {
    test('parses the invite_code_required flag', () async {
      when(() => adapter.fetch(any(), any(), any())).thenAnswer(
        (_) async => _jsonBody(
          {
            'needs_bootstrap': false,
            'registration_enabled': true,
            'invite_code_required': true,
          },
          200,
        ),
      );

      final result = await repository.bootstrapStatus();

      expect(result.isOk, isTrue);
      expect(result.value, isA<BootstrapStatus>());
      expect(result.value.inviteCodeRequired, isTrue);
    });

    test('a server that has not shipped the flag yet is "not required"',
        () async {
      when(() => adapter.fetch(any(), any(), any())).thenAnswer(
        (_) async => _jsonBody(
          {
            'needs_bootstrap': false,
            'registration_enabled': true,
          },
          200,
        ),
      );

      final result = await repository.bootstrapStatus();

      expect(result.isOk, isTrue);
      expect(result.value.inviteCodeRequired, isFalse);
    });
  });
}
