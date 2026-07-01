import 'package:aistudio_mobile/core/config/env.dart';
import 'package:aistudio_mobile/core/network/interceptors/error_interceptor.dart';
import 'package:aistudio_mobile/core/network/interceptors/logging_interceptor.dart';
import 'package:dio/dio.dart';

/// Factory that constructs a fully-configured Dio instance.
///
/// [baseUrl] defaults to the compile-time default from [Env.defaultApiUrl]
/// but can be overridden at runtime (user sets their server address).
Dio createDioClient({String? baseUrl}) {
  final dio = Dio(
    BaseOptions(
      baseUrl: baseUrl ?? Env.defaultApiUrl,
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 30),
      sendTimeout: const Duration(seconds: 15),
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
      },
      responseType: ResponseType.json,
    ),
  );

  dio.interceptors.addAll([
    ErrorInterceptor(),
    if (Env.isDev) LoggingInterceptor(),
  ]);

  return dio;
}
