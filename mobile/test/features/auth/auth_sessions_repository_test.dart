import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/network/interceptors/error_interceptor.dart';
import 'package:manhwamaniacs/features/auth/repositories/auth_repository_impl.dart';
import 'package:mocktail/mocktail.dart';

/// The wire contract for the three session endpoints, driven through Dio's own
/// pipeline (with the production [ErrorInterceptor]) rather than a hand-rolled
/// fake — the shapes here are what `backend/routes/auth.py` actually sends and
/// expects, so a drift on either side fails a test instead of a phone.
class _MockHttpClientAdapter extends Mock implements HttpClientAdapter {}

class _FakeRequestOptions extends Fake implements RequestOptions {}

ResponseBody _jsonBody(Object body, int statusCode) => ResponseBody.fromString(
      jsonEncode(body),
      statusCode,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );

/// A 204, which is what every mutation on this surface answers with.
ResponseBody _noContent() => ResponseBody.fromString('', 204);

Map<String, dynamic> _sessionJson({
  required int id,
  bool current = false,
  String? userAgent = 'Dart/3.5 (dart:io)',
}) =>
    {
      'id': id,
      'created_at': '2026-09-01T08:30:00',
      'last_used_at': '2026-09-05T10:00:00',
      'expires_at': '2026-10-01T08:30:00',
      'user_agent': userAgent,
      'ip_address': '10.0.0.4',
      'current': current,
    };

void main() {
  setUpAll(() => registerFallbackValue(_FakeRequestOptions()));

  late _MockHttpClientAdapter adapter;
  late Dio dio;
  late AuthRepositoryImpl repository;

  setUp(() {
    adapter = _MockHttpClientAdapter();
    dio = Dio(BaseOptions(baseUrl: 'https://mm.test'))
      ..httpClientAdapter = adapter
      ..interceptors.add(ErrorInterceptor());
    repository = AuthRepositoryImpl(dio);
  });

  RequestOptions capture() =>
      verify(() => adapter.fetch(captureAny(), any(), any()))
          .captured
          .single as RequestOptions;

  group('changePassword', () {
    test('posts both passwords in the body of /auth/change-password', () async {
      when(() => adapter.fetch(any(), any(), any()))
          .thenAnswer((_) async => _noContent());

      final result = await repository.changePassword(
        currentPassword: 'old-password',
        newPassword: 'new-password',
      );

      expect(result.isOk, isTrue);
      final request = capture();
      expect(request.method, 'POST');
      expect(request.path, '/auth/change-password');
      final body = request.data as Map<String, dynamic>;
      expect(body['current_password'], 'old-password');
      expect(body['new_password'], 'new-password');
    });

    // A password in a URL is a password in the server's access log, in every
    // proxy in between, and in the crash reporter. It travels in the body.
    test('never puts a password in the URL', () async {
      when(() => adapter.fetch(any(), any(), any()))
          .thenAnswer((_) async => _noContent());

      await repository.changePassword(
        currentPassword: 'correct-horse',
        newPassword: 'battery-staple',
      );

      final uri = capture().uri;
      expect(uri.query, isEmpty);
      expect(uri.toString().contains('correct-horse'), isFalse);
      expect(uri.toString().contains('battery-staple'), isFalse);
    });

    test('a wrong current password surfaces as 401 invalid_credentials',
        () async {
      when(() => adapter.fetch(any(), any(), any())).thenAnswer(
        (_) async => _jsonBody(
          {
            'code': 'invalid_credentials',
            'message': 'Current password is incorrect.',
          },
          401,
        ),
      );

      final result = await repository.changePassword(
        currentPassword: 'wrong',
        newPassword: 'new-password',
      );

      expect(result.isErr, isTrue);
      final error = result.error as ApiError;
      expect(error.statusCode, 401);
      expect(error.code, 'invalid_credentials');
      // The server's own wording is what the UI shows — not a client rewrite.
      expect(error.userMessage, 'Current password is incorrect.');
    });

    test('a refused new password surfaces as 422 weak_password', () async {
      when(() => adapter.fetch(any(), any(), any())).thenAnswer(
        (_) async => _jsonBody(
          {
            'code': 'weak_password',
            'message': 'Password must be at least 8 characters.',
          },
          422,
        ),
      );

      final result = await repository.changePassword(
        currentPassword: 'old-password',
        newPassword: 'short',
      );

      expect((result.error as ApiError).code, 'weak_password');
    });
  });

  group('sessions', () {
    test('parses the list and the server-set current flag', () async {
      when(() => adapter.fetch(any(), any(), any())).thenAnswer(
        (_) async => _jsonBody(
          [
            _sessionJson(id: 1, current: true),
            _sessionJson(id: 2, userAgent: 'Mozilla/5.0 (Windows NT 10.0)'),
          ],
          200,
        ),
      );

      final result = await repository.sessions();

      expect(result.isOk, isTrue);
      expect(result.value.map((s) => s.id), [1, 2]);
      expect(result.value.singleWhere((s) => s.isCurrent).id, 1);
      expect(capture().path, '/auth/sessions');
    });

    test('an empty list is a value, not an error', () async {
      when(() => adapter.fetch(any(), any(), any()))
          .thenAnswer((_) async => _jsonBody(<Object>[], 200));

      final result = await repository.sessions();

      expect(result.isOk, isTrue);
      expect(result.value, isEmpty);
    });
  });

  group('revokeSession', () {
    test('DELETEs the session by id', () async {
      when(() => adapter.fetch(any(), any(), any()))
          .thenAnswer((_) async => _noContent());

      final result = await repository.revokeSession(42);

      expect(result.isOk, isTrue);
      final request = capture();
      expect(request.method, 'DELETE');
      expect(request.path, '/auth/sessions/42');
    });

    test('a session that is already gone is a 404 not_found', () async {
      when(() => adapter.fetch(any(), any(), any())).thenAnswer(
        (_) async =>
            _jsonBody({'code': 'not_found', 'message': 'Session not found.'}, 404),
      );

      final result = await repository.revokeSession(42);

      expect((result.error as ApiError).code, 'not_found');
    });
  });

  group('logoutAll', () {
    test('posts to /auth/logout-all', () async {
      when(() => adapter.fetch(any(), any(), any()))
          .thenAnswer((_) async => _noContent());

      final result = await repository.logoutAll();

      expect(result.isOk, isTrue);
      final request = capture();
      expect(request.method, 'POST');
      expect(request.path, '/auth/logout-all');
    });

    test('an unreachable server is an error, never a silent success', () async {
      when(() => adapter.fetch(any(), any(), any())).thenThrow(
        DioException.connectionError(
          requestOptions: RequestOptions(path: '/auth/logout-all'),
          reason: 'blackholed',
        ),
      );

      final result = await repository.logoutAll();

      expect(result.isErr, isTrue);
      expect(result.error, isA<NetworkError>());
    });
  });
}
