import 'package:dio/dio.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';

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
          host: _hostOf(err),
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
          host: _hostOf(err),
        );

      case DioExceptionType.unknown:
        if (err.error is AppError) return err.error! as AppError;
        return UnknownError(message: err.message ?? 'Unknown error', cause: err.error);
    }
  }

  /// Best-effort host for the failed request, for a user-facing message that
  /// names the unreachable server. Falls back to the configured base URL.
  String? _hostOf(DioException err) {
    final host = err.requestOptions.uri.host;
    if (host.isNotEmpty) return host;
    return Uri.tryParse(err.requestOptions.baseUrl)?.host;
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
