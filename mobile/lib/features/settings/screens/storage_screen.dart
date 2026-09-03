import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/features/settings/providers/settings_provider.dart';
import 'package:manhwamaniacs/shared/widgets/glass_card.dart';
import 'package:manhwamaniacs/shared/widgets/skeleton_box.dart';

/// Formats a byte count as a compact human-readable size ("4.2 MB").
String formatStorageBytes(int bytes) {
  if (bytes <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  var value = bytes.toDouble();
  var unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex++;
  }
  final formatted = unitIndex == 0 ? value.toStringAsFixed(0) : value.toStringAsFixed(1);
  return '$formatted ${units[unitIndex]}';
}

/// The device-storage control center: how much space caches use, and one
/// place to reclaim it.
// TODO(1c-M3): add a downloaded-chapters storage card once the on-device
// store ships (real on-device bytes, not the deleted server download queue).
class StorageScreen extends ConsumerWidget {
  const StorageScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          tooltip: 'Back',
          onPressed: () =>
              context.canPop() ? context.pop() : context.go(Routes.settings),
        ),
        title: const Text('Storage'),
      ),
      body: ListView(
        padding: const EdgeInsets.all(AppSpacing.xl2),
        children: const [
          _ImageCacheCard(),
          SizedBox(height: AppSpacing.xl2),
          _MetadataCacheCard(),
        ],
      ),
    );
  }
}

class _ImageCacheCard extends ConsumerWidget {
  const _ImageCacheCard();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final usageAsync = ref.watch(cacheUsageProvider);

    return GlassCard(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.image_outlined, color: AppColors.primary, size: 20),
              const SizedBox(width: AppSpacing.sm),
              Text('Image cache', style: AppTypography.h4),
            ],
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            'Thumbnails and pages cached for smooth scrolling. Safe to clear '
            'any time — it rebuilds automatically as you browse.',
            style: AppTypography.bodySm.copyWith(color: AppColors.muted, height: 1.5),
          ),
          const SizedBox(height: AppSpacing.md),
          usageAsync.when(
            loading: () => const SkeletonBox(width: 100, height: 20),
            error: (_, __) => Text(
              'Unable to read cache size',
              style: AppTypography.body.copyWith(color: AppColors.muted),
            ),
            data: (bytes) => Text(
              formatStorageBytes(bytes),
              style: AppTypography.h3,
            ),
          ),
          const SizedBox(height: AppSpacing.lg),
          OutlinedButton(
            onPressed: () async {
              await ref.read(settingsActionsProvider).clearImageCache();
              if (context.mounted) {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Image cache cleared.')),
                );
              }
            },
            child: const Text('Clear image cache'),
          ),
        ],
      ),
    );
  }
}

class _MetadataCacheCard extends ConsumerWidget {
  const _MetadataCacheCard();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return GlassCard(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.refresh_outlined, color: AppColors.accent, size: 20),
              const SizedBox(width: AppSpacing.sm),
              Text('Metadata cache', style: AppTypography.h4),
            ],
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            'Library, search and reading-progress data held in memory. '
            'Clearing it forces a fresh fetch from your server on next use.',
            style: AppTypography.bodySm.copyWith(color: AppColors.muted, height: 1.5),
          ),
          const SizedBox(height: AppSpacing.lg),
          OutlinedButton(
            onPressed: () {
              ref.read(settingsActionsProvider).clearMetadataCache();
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Metadata cache cleared.')),
              );
            },
            child: const Text('Clear metadata cache'),
          ),
        ],
      ),
    );
  }
}
