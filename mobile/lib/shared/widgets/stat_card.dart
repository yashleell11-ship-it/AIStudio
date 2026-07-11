import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/shared/widgets/glass_card.dart';

enum StatAccent { violet, cyan, emerald, amber }

class StatCard extends StatelessWidget {
  const StatCard({
    super.key,
    required this.icon,
    required this.value,
    required this.label,
    required this.accent,
  });

  final IconData icon;
  final String value;
  final String label;
  final StatAccent accent;

  @override
  Widget build(BuildContext context) {
    final (accentColor, glowColor) = switch (accent) {
      StatAccent.violet => (AppColors.violet400, AppColors.primary),
      StatAccent.cyan   => (AppColors.cyan400,   AppColors.accent),
      StatAccent.emerald => (AppColors.emerald400, AppColors.success),
      StatAccent.amber  => (AppColors.amber400,  AppColors.warning),
    };

    return GlassCard(
      glowColor: glowColor,
      padding: const EdgeInsets.all(AppSpacing.xl2),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(AppRadius.md),
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [
                      accentColor.withAlpha(60),
                      accentColor.withAlpha(20),
                    ],
                  ),
                  border: Border.all(color: accentColor.withAlpha(50)),
                ),
                child: Icon(icon, size: 18, color: accentColor),
              ),
              // Subtle colored dot
              Container(
                width: 6,
                height: 6,
                decoration: BoxDecoration(
                  color: accentColor.withAlpha(160),
                  shape: BoxShape.circle,
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.xl),
          Text(
            value,
            style: AppTypography.h1.copyWith(
              fontFeatures: const [FontFeature.tabularFigures()],
              color: AppColors.fg,
            ),
          ),
          const SizedBox(height: AppSpacing.xxs),
          Text(
            label,
            style: AppTypography.caption.copyWith(
              fontWeight: FontWeight.w500,
              letterSpacing: 0.4,
            ),
          ),
          const SizedBox(height: AppSpacing.md),
          // Colored accent bar at bottom
          Container(
            height: 2,
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [accentColor, accentColor.withAlpha(0)],
              ),
              borderRadius: BorderRadius.circular(AppRadius.full),
            ),
          ),
        ],
      ),
    );
  }
}
