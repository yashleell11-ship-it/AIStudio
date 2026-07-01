import 'dart:ui' show FontFeature;

import 'package:aistudio_mobile/app/theme/app_colors.dart';
import 'package:aistudio_mobile/app/theme/app_spacing.dart';
import 'package:aistudio_mobile/app/theme/app_typography.dart';
import 'package:aistudio_mobile/shared/widgets/glass_card.dart';
import 'package:flutter/material.dart';

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
    final accentColor = switch (accent) {
      StatAccent.violet => AppColors.violet400,
      StatAccent.cyan => AppColors.cyan400,
      StatAccent.emerald => AppColors.success,
      StatAccent.amber => AppColors.warning,
    };

    return GlassCard(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(AppRadius.md),
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [
                  accentColor.withAlpha(51),
                  accentColor.withAlpha(13),
                ],
              ),
            ),
            child: Icon(icon, size: 16, color: accentColor),
          ),
          const SizedBox(height: AppSpacing.md),
          Text(
            value,
            style: AppTypography.h2.copyWith(fontFeatures: const [
              FontFeature.tabularFigures(),
            ]),
          ),
          const SizedBox(height: 2),
          Text(
            label,
            style: AppTypography.caption,
          ),
        ],
      ),
    );
  }
}
