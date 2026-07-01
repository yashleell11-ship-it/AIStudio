import 'package:aistudio_mobile/app/theme/app_colors.dart';
import 'package:aistudio_mobile/app/theme/app_typography.dart';
import 'package:flutter/material.dart';

/// Temporary screen shown for routes whose feature screen has not been built yet.
class PlaceholderScreen extends StatelessWidget {
  const PlaceholderScreen({super.key, required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(label)),
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.construction, size: 48, color: AppColors.muted),
            const SizedBox(height: 16),
            Text(label, style: AppTypography.h3),
            const SizedBox(height: 8),
            Text(
              'Screen not yet implemented',
              style: AppTypography.body.copyWith(color: AppColors.muted),
            ),
          ],
        ),
      ),
    );
  }
}
