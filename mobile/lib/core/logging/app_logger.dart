import 'package:logger/logger.dart';

final appLogger = AppLogger._();

class AppLogger {
  AppLogger._();

  late final Logger _logger = Logger(
    printer: PrettyPrinter(
      methodCount: 1,
      errorMethodCount: 8,
      lineLength: 100,
      colors: true,
      printEmojis: true,
      dateTimeFormat: DateTimeFormat.onlyTimeAndSinceStart,
    ),
    level: Level.debug,
  );

  void d(dynamic message, [dynamic error, StackTrace? stackTrace]) =>
      _logger.d(message, error: error, stackTrace: stackTrace);

  void i(dynamic message, [dynamic error, StackTrace? stackTrace]) =>
      _logger.i(message, error: error, stackTrace: stackTrace);

  void w(dynamic message, [dynamic error, StackTrace? stackTrace]) =>
      _logger.w(message, error: error, stackTrace: stackTrace);

  void e(dynamic message, [dynamic error, StackTrace? stackTrace]) =>
      _logger.e(message, error: error, stackTrace: stackTrace);
}
