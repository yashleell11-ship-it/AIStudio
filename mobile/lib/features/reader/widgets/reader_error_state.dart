import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/reader/theme/reader_colors.dart';

class ReaderErrorState extends StatelessWidget {
  const ReaderErrorState({
    super.key,
    required this.error,
    required this.onRetry,
    required this.onBack,
  });

  final AppError error;
  final VoidCallback onRetry;
  final VoidCallback onBack;

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: ReaderColors.bg,
      child: Center(
        child: Padding(
          padding: EdgeInsets.all(context.space.xl2),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, color: ReaderColors.danger, size: 40),
              SizedBox(height: context.space.md),
              Text(
                error.userMessage,
                // Explicit ink: this sits on the reader-owned dark surface,
                // where the ambient theme foreground may be dark.
                style: context.text.body.copyWith(color: ReaderColors.fg),
                textAlign: TextAlign.center,
              ),
              SizedBox(height: context.space.xl2),
              FilledButton(onPressed: onRetry, child: const Text('Retry')),
              SizedBox(height: context.space.sm),
              TextButton(onPressed: onBack, child: const Text('Go back')),
            ],
          ),
        ),
      ),
    );
  }
}
