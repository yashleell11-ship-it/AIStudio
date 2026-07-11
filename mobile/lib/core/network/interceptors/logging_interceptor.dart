import 'package:dio/dio.dart';
import 'package:manhwamaniacs/core/logging/app_logger.dart';

/// Logs all outbound requests and inbound responses at debug level.
class LoggingInterceptor extends Interceptor {
  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    appLogger.d('→ ${options.method} ${options.uri}');
    handler.next(options);
  }

  @override
  void onResponse(Response<dynamic> response, ResponseInterceptorHandler handler) {
    appLogger.d(
      '← ${response.statusCode} ${response.requestOptions.method} '
      '${response.requestOptions.uri}',
    );
    handler.next(response);
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) {
    appLogger.e(
      '✗ ${err.requestOptions.method} ${err.requestOptions.uri}',
      err,
      err.stackTrace,
    );
    handler.next(err);
  }
}
