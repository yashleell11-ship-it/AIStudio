import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/network/interceptors/error_interceptor.dart';

/// Simulates an unreachable server by throwing a connection error instead of
/// performing a real fetch, so the interceptor's mapping runs end-to-end.
class _FailingAdapter implements HttpClientAdapter {
  _FailingAdapter(this.type);

  final DioExceptionType type;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    throw DioException(
      requestOptions: options,
      type: type,
      error: 'boom',
    );
  }

  @override
  void close({bool force = false}) {}
}

Dio _dio(DioExceptionType type) {
  return Dio(BaseOptions(baseUrl: 'https://app.manhwamaniacs.xyz'))
    ..httpClientAdapter = _FailingAdapter(type)
    ..interceptors.add(ErrorInterceptor());
}

void main() {
  group('ErrorInterceptor', () {
    test('maps a connection error to a host-aware NetworkError', () async {
      NetworkError? mapped;
      try {
        await _dio(DioExceptionType.connectionError)
            .post<dynamic>('/auth/login');
      } on DioException catch (e) {
        mapped = e.error as NetworkError?;
      }

      expect(mapped, isNotNull);
      expect(mapped!.host, 'app.manhwamaniacs.xyz');
      expect(mapped.userMessage, contains('app.manhwamaniacs.xyz'));
    });

    test('maps a bad certificate to a host-aware NetworkError', () async {
      NetworkError? mapped;
      try {
        await _dio(DioExceptionType.badCertificate).get<dynamic>('/health');
      } on DioException catch (e) {
        mapped = e.error as NetworkError?;
      }

      expect(mapped, isNotNull);
      expect(mapped!.host, 'app.manhwamaniacs.xyz');
    });
  });

  group('NetworkError.userMessage', () {
    test('falls back to a generic message when the host is unknown', () {
      expect(
        const NetworkError(message: 'x').userMessage,
        'Network error — check your connection.',
      );
    });

    test('names the server when the host is known', () {
      expect(
        const NetworkError(message: 'x', host: 'example.test').userMessage,
        "Can't reach the server at example.test — check your connection.",
      );
    });
  });
}
