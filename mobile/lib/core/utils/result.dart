import 'package:manhwamaniacs/core/error/app_error.dart';

/// Lightweight Result type — avoids try/catch at call sites.
sealed class Result<T> {
  const Result();

  bool get isOk => this is Ok<T>;
  bool get isErr => this is Err<T>;

  T get value => (this as Ok<T>).value;
  AppError get error => (this as Err<T>).error;

  R fold<R>({
    required R Function(T value) ok,
    required R Function(AppError error) err,
  }) {
    return switch (this) {
      Ok(:final value) => ok(value),
      Err(:final error) => err(error),
    };
  }

  Result<R> map<R>(R Function(T value) f) {
    return switch (this) {
      Ok(:final value) => Ok(f(value)),
      Err(:final error) => Err(error),
    };
  }

  Future<Result<R>> asyncMap<R>(Future<R> Function(T value) f) async {
    return switch (this) {
      Ok(:final value) => Ok(await f(value)),
      Err(:final error) => Err(error),
    };
  }
}

final class Ok<T> extends Result<T> {
  const Ok(this.value);
  @override
  final T value;
}

final class Err<T> extends Result<T> {
  const Err(this.error);
  @override
  final AppError error;
}
