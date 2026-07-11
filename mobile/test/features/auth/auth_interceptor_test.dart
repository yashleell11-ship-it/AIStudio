import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/network/interceptors/auth_interceptor.dart';

/// Captures the outgoing request and returns a canned response without touching
/// the network, so the interceptor can be exercised end-to-end.
class _CapturingAdapter implements HttpClientAdapter {
  _CapturingAdapter({this.statusCode = 200});

  final int statusCode;
  RequestOptions? lastRequest;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    lastRequest = options;
    return ResponseBody.fromString(
      '{}',
      statusCode,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

Dio _dio(AuthInterceptor interceptor, HttpClientAdapter adapter) {
  return Dio(BaseOptions(baseUrl: 'https://example.test'))
    ..httpClientAdapter = adapter
    ..interceptors.add(interceptor);
}

void main() {
  group('AuthInterceptor', () {
    test('attaches the bearer token when present', () async {
      final store = AuthTokenStore()..token = 'abc123';
      final adapter = _CapturingAdapter();
      final dio = _dio(
        AuthInterceptor(tokenStore: store, onUnauthorized: () {}),
        adapter,
      );

      await dio.get<dynamic>('/downloads');

      expect(adapter.lastRequest!.headers['Authorization'], 'Bearer abc123');
    });

    test('omits the header when there is no token', () async {
      final adapter = _CapturingAdapter();
      final dio = _dio(
        AuthInterceptor(tokenStore: AuthTokenStore(), onUnauthorized: () {}),
        adapter,
      );

      await dio.get<dynamic>('/downloads');

      expect(
        adapter.lastRequest!.headers.containsKey('Authorization'),
        isFalse,
      );
    });

    test('invokes onUnauthorized on a 401 for a protected route', () async {
      var expired = 0;
      final dio = _dio(
        AuthInterceptor(
          tokenStore: AuthTokenStore()..token = 't',
          onUnauthorized: () => expired++,
        ),
        _CapturingAdapter(statusCode: 401),
      );

      await expectLater(
        dio.get<dynamic>('/downloads'),
        throwsA(isA<DioException>()),
      );
      expect(expired, 1);
    });

    test('ignores a 401 from the public login endpoint', () async {
      var expired = 0;
      final dio = _dio(
        AuthInterceptor(
          tokenStore: AuthTokenStore(),
          onUnauthorized: () => expired++,
        ),
        _CapturingAdapter(statusCode: 401),
      );

      await expectLater(
        dio.post<dynamic>('/auth/login'),
        throwsA(isA<DioException>()),
      );
      expect(expired, 0);
    });

    test('ignores a 401 from the launch-time /auth/me probe', () async {
      var expired = 0;
      final dio = _dio(
        AuthInterceptor(
          tokenStore: AuthTokenStore()..token = 'stale',
          onUnauthorized: () => expired++,
        ),
        _CapturingAdapter(statusCode: 401),
      );

      await expectLater(
        dio.get<dynamic>('/auth/me'),
        throwsA(isA<DioException>()),
      );
      expect(expired, 0);
    });
  });
}
