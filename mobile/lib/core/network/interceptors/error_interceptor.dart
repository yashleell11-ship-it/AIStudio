import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:dio/dio.dart';

/// Converts DioException into domain AppError and re-throws.
///
/// Centralises error mapping so repositories never handle raw DioExceptions.
class ErrorInterceptor extends Interceptor {
  @override
  void onError(DioException err, ErrorInterceptorHandler handler) {
    final appError = _mapDioError(err);
    handler.reject(
      DioException(
        requestOptions: err.requestOptions,
        error: appError,
        type: err.type,
        response: err.response,
        stackTrace: err.stackTrace,
      ),
    );
  }

  AppError _mapDioError(DioException err) {
    switch (err.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
      case DioExceptionType.transformTimeout:
        return const TimeoutError();

      case DioExceptionType.connectionError:
        return NetworkError(
          message: err.message ?? 'Connection failed',
          cause: err.error,
        );

      case DioExceptionType.badResponse:
        final response = err.response;
        if (response == null) {
          return NetworkError(message: 'Empty response', cause: err);
        }
        return _mapApiResponse(response);

      case DioExceptionType.cancel:
        return const UnknownError(message: 'Request cancelled');

      case DioExceptionType.badCertificate:
        return NetworkError(
          message: 'TLS certificate error',
          cause: err.error,
        );

      case DioExceptionType.unknown:
        if (err.error is AppError) return err.error! as AppError;
        return UnknownError(message: err.message ?? 'Unknown error', cause: err.error);
    }
  }

  AppError _mapApiResponse(Response<dynamic> response) {
    try {
      final body = response.data as Map<String, dynamic>;
      return ApiError(
        statusCode: response.statusCode ?? 0,
        code: body['code'] as String? ?? 'unknown',
        message: body['message'] as String? ?? 'Unknown error',
        details: body['details'],
      );
    } catch (_) {
      return ApiError(
        statusCode: response.statusCode ?? 0,
        code: 'unknown',
        message: 'HTTP ${response.statusCode}',
      );
    }
  }
}
