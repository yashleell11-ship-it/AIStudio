import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/shared/widgets/premium/hero_heading.dart';

/// Warm brand mark + gradient hero title + subtitle shown at the top of the
/// login / register screens, so both flows share one consistent "Eclipse Warm"
/// header.
class AuthHeader extends StatelessWidget {
  const AuthHeader({required this.title, required this.subtitle, super.key});

  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Warm amber → ember brand mark.
        Container(
          width: 56,
          height: 56,
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [context.colors.primary, context.colors.accent],
            ),
            borderRadius: BorderRadius.circular(AppRadius.lg),
            boxShadow: [
              BoxShadow(
                color: context.colors.primary.withValues(alpha: 0.28),
                blurRadius: 24,
                spreadRadius: -4,
              ),
            ],
          ),
          child: Center(
            child: Text(
              'M',
              style: AppTypography.h1.copyWith(color: Colors.white),
            ),
          ),
        ),
        const SizedBox(height: AppSpacing.xl2),
        HeroHeading(text: title, fontSize: 38),
        const SizedBox(height: AppSpacing.sm),
        Text(
          subtitle,
          style: AppTypography.body.copyWith(color: context.colors.muted),
        ),
      ],
    );
  }
}
