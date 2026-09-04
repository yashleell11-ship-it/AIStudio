import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';

/// Maps [AsyncValue] to loading / error / data widgets.
///
/// Keeps the pattern consistent across all screens and avoids per-widget
/// switch statements on AsyncValue states.
class AsyncValueWidget<T> extends StatelessWidget {
  const AsyncValueWidget({
    super.key,
    required this.value,
    required this.data,
    this.loading,
    this.error,
  });

  final AsyncValue<T> value;
  final Widget Function(T data) data;
  final Widget? loading;
  final Widget Function(AppError error)? error;

  @override
  Widget build(BuildContext context) {
    return value.when(
      loading: () => loading ?? const _DefaultLoading(),
      error: (e, _) {
        final appError = e is AppError
            ? e
            : UnknownError(message: e.toString(), cause: e);
        return error?.call(appError) ?? _DefaultError(appError);
      },
      data: data,
    );
  }
}

class _DefaultLoading extends StatelessWidget {
  const _DefaultLoading();

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: CircularProgressIndicator(strokeWidth: 2),
    );
  }
}

class _DefaultError extends StatelessWidget {
  const _DefaultError(this.error);

  final AppError error;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.error_outline, color: context.colors.danger, size: 40),
            const SizedBox(height: 12),
            Text(
              error.userMessage,
              style: context.text.body,
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }
}