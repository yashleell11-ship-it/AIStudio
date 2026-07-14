import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_provider.dart';
import 'package:manhwamaniacs/features/downloads/utils/download_formatters.dart';
import 'package:manhwamaniacs/features/settings/providers/settings_provider.dart';
import 'package:manhwamaniacs/shared/widgets/glass_card.dart';
import 'package:manhwamaniacs/shared/widgets/skeleton_box.dart';

/// The device-storage control center: how much space downloads and caches
/// use, and one place to reclaim it. Reuses the same cache-clearing actions
/// previously on Settings -> General (moved here, not duplicated, so
/// "how much space am I using" lives in exactly one place).
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
        children: [
          _DownloadsStorageCard(onManage: () => context.go(Routes.downloads)),
          const SizedBox(height: AppSpacing.xl2),
          const _ImageCacheCard(),
          const SizedBox(height: AppSpacing.xl2),
          const _MetadataCacheCard(),
        ],
      ),
    );
  }
}

class _DownloadsStorageCard extends ConsumerWidget {
  const _DownloadsStorageCard({required this.onManage});

  final VoidCallback onManage;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final metricsAsync = ref.watch(storageMetricsProvider);

    return GlassCard(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.download_outlined, color: AppColors.accent, size: 20),
              const SizedBox(width: AppSpacing.sm),
              Text('Downloaded chapters', style: AppTypography.h4),
            ],
          ),
          const SizedBox(height: AppSpacing.lg),
          metricsAsync.when(
            loading: () => const Column(
              children: [
                SkeletonBox(width: double.infinity, height: 20),
                SizedBox(height: AppSpacing.sm),
                SkeletonBox(width: 160, height: 16),
              ],
            ),
            error: (_, __) => Text(
              'Unable to read download storage.',
              style: AppTypography.body.copyWith(color: AppColors.muted),
            ),
            data: (metrics) => _StorageBar(
              usedBytes: metrics.storageUsedBytes,
              freeBytes: metrics.storageFreeBytes,
              completedCount: metrics.completed,
            ),
          ),
          const SizedBox(height: AppSpacing.lg),
          OutlinedButton.icon(
            onPressed: onManage,
            icon: const Icon(Icons.tune_outlined, size: 18),
            label: const Text('Manage downloads'),
          ),
        ],
      ),
    );
  }
}

class _StorageBar extends StatelessWidget {
  const _StorageBar({
    required this.usedBytes,
    required this.freeBytes,
    required this.completedCount,
  });

  final int usedBytes;
  final int freeBytes;
  final int completedCount;

  @override
  Widget build(BuildContext context) {
    final total = usedBytes + freeBytes;
    final usedFraction = total > 0 ? (usedBytes / total).clamp(0.0, 1.0) : 0.0;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(AppRadius.full),
          child: LinearProgressIndicator(
            value: usedFraction,
            minHeight: 8,
            backgroundColor: AppColors.fg.withAlpha(26),
            valueColor: const AlwaysStoppedAnimation<Color>(AppColors.accent),
          ),
        ),
        const SizedBox(height: AppSpacing.sm),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              '${formatDownloadBytes(usedBytes)} used',
              style: AppTypography.bodySm.copyWith(color: AppColors.fg),
            ),
            Text(
              '${formatDownloadBytes(freeBytes)} free',
              style: AppTypography.bodySm.copyWith(color: AppColors.muted),
            ),
          ],
        ),
        const SizedBox(height: AppSpacing.xs),
        Text(
          '$completedCount chapter${completedCount == 1 ? '' : 's'} downloaded',
          style: AppTypography.caption,
        ),
      ],
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
              formatDownloadBytes(bytes),
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
