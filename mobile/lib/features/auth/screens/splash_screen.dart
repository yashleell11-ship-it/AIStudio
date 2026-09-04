import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';

/// Shown while the app validates a stored session on cold start, so the user is
/// never bounced to login before the auth state resolves.
///
/// Warm "Eclipse Warm" branded loader: an amber → ember brand mark over the
/// void background with a matching amber progress spinner.
class SplashScreen extends StatelessWidget {
  const SplashScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: context.colors.bg,
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 72,
              height: 72,
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [context.colors.primary, context.colors.accent],
                ),
                borderRadius: BorderRadius.circular(AppRadius.xl),
                boxShadow: [
                  BoxShadow(
                    color: context.colors.primary.withValues(alpha: 0.3),
                    blurRadius: 32,
                    spreadRadius: -4,
                  ),
                ],
              ),
              child: Center(
                child: Text(
                  'M',
                  style: AppTypography.displayMd.copyWith(color: Colors.white),
                ),
              ),
            ),
            const SizedBox(height: AppSpacing.xl),
            Text(
              'ManhwaManiacs',
              style: AppTypography.labelLg.copyWith(
                color: context.colors.muted,
                letterSpacing: 2,
              ),
            ),
            const SizedBox(height: AppSpacing.xl2),
            SizedBox(
              width: 22,
              height: 22,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                valueColor: AlwaysStoppedAnimation<Color>(context.colors.primary),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
