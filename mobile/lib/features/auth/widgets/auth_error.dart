import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';

/// Inline error banner shown beneath the auth form fields.
class AuthError extends StatelessWidget {
  const AuthError({required this.message, super.key});

  final String message;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: context.colors.danger.withAlpha(24),
        borderRadius: BorderRadius.circular(AppRadius.md),
        border: Border.all(color: context.colors.danger.withAlpha(90)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Row(
          children: [
            Icon(Icons.error_outline, color: context.colors.danger, size: 18),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Text(
                message,
                style: AppTypography.bodySm.copyWith(color: context.colors.fg),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
