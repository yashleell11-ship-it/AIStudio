import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';

/// Brand mark + title + subtitle shown at the top of the login / register
/// screens, so both flows share one consistent header.
class AuthHeader extends StatelessWidget {
  const AuthHeader({required this.title, required this.subtitle, super.key});

  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 56,
          height: 56,
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [AppColors.primary, AppColors.violet600],
            ),
            borderRadius: BorderRadius.circular(AppRadius.lg),
          ),
          child: Center(
            child: Text('M', style: AppTypography.h1),
          ),
        ),
        const SizedBox(height: AppSpacing.lg),
        Text(title, style: AppTypography.h2),
        const SizedBox(height: AppSpacing.sm),
        Text(
          subtitle,
          style: AppTypography.body.copyWith(color: AppColors.muted),
        ),
      ],
    );
  }
}
