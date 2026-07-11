import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/utils/result.dart';

void main() {
  group('Result', () {
    test('Ok.isOk is true, isErr is false', () {
      const result = Ok(42);
      expect(result.isOk, isTrue);
      expect(result.isErr, isFalse);
      expect(result.value, 42);
    });

    test('Err.isErr is true, isOk is false', () {
      const error = NetworkError(message: 'no connection');
      const result = Err<int>(error);
      expect(result.isErr, isTrue);
      expect(result.isOk, isFalse);
      expect(result.error, error);
    });

    test('fold calls ok branch for Ok', () {
      const result = Ok(10);
      final out = result.fold(ok: (v) => v * 2, err: (_) => -1);
      expect(out, 20);
    });

    test('fold calls err branch for Err', () {
      const result = Err<int>(TimeoutError());
      final out = result.fold(ok: (v) => v, err: (_) => -99);
      expect(out, -99);
    });

    test('map transforms value for Ok', () {
      const result = Ok(5);
      final mapped = result.map((v) => v.toString());
      expect(mapped.value, '5');
    });

    test('map passes through error for Err', () {
      const error = TimeoutError();
      const result = Err<int>(error);
      final mapped = result.map((v) => v.toString());
      expect(mapped.isErr, isTrue);
      expect(mapped.error, error);
    });

    test('asyncMap transforms async value for Ok', () async {
      const result = Ok(3);
      final mapped = await result.asyncMap((v) async => v + 1);
      expect(mapped.value, 4);
    });
  });

  group('AppError.userMessage', () {
    test('ApiError returns its message', () {
      const e = ApiError(statusCode: 404, code: 'not_found', message: 'Not found');
      expect(e.userMessage, 'Not found');
      expect(e.isNotFound, isTrue);
    });

    test('NetworkError returns generic message', () {
      const e = NetworkError(message: 'ECONNREFUSED');
      expect(e.userMessage, contains('connection'));
    });

    test('TimeoutError returns timeout message', () {
      expect(const TimeoutError().userMessage, contains('timed out'));
    });
  });
}
