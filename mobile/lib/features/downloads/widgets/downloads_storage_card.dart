import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/features/downloads/models/retention_policy.dart';
import 'package:manhwamaniacs/features/downloads/models/storage_cap.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_storage_providers.dart';
import 'package:manhwamaniacs/features/downloads/providers/storage_settings_provider.dart';
import 'package:manhwamaniacs/shared/widgets/glass_card.dart';
import 'package:manhwamaniacs/shared/widgets/skeleton_box.dart';

/// Formats a byte count as a compact human-readable size ("4.2 MB"). Shared
/// with the image-cache card above it on the Storage screen.
String formatDownloadBytes(int bytes) {
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

/// The on-device chapter store's own storage card (spec §3b): real device
/// bytes (not server bytes — the old, deleted server-download queue used
/// to conflate the two), a cap picker, the read-then-expire interval, a
/// per-series breakdown, and "Free up space".
class DownloadsStorageCard extends ConsumerWidget {
  const DownloadsStorageCard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final hasScope = ref.watch(activeDownloadsScopeIdProvider) != null;
    if (!hasScope) return const SizedBox.shrink();

    final totalAsync = ref.watch(totalDeviceDownloadBytesProvider);
    final cap = ref.watch(storageCapProvider);
    final breakdownAsync = ref.watch(seriesStorageBreakdownProvider);
    final isIOS = Theme.of(context).platform == TargetPlatform.iOS;

    return GlassCard(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.download_done_outlined, color: AppColors.primary, size: 20),
              const SizedBox(width: AppSpacing.sm),
              Text('Downloaded chapters', style: AppTypography.h4),
            ],
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            'Chapters saved to this phone for offline reading. Deleting a '
            'chapter here never rewinds your reading progress — it stays on '
            'the server and can be re-downloaded any time.',
            style: AppTypography.bodySm.copyWith(color: AppColors.muted, height: 1.5),
          ),
          const SizedBox(height: AppSpacing.md),
          totalAsync.when(
            loading: () => const SkeletonBox(width: 120, height: 20),
            error: (_, __) => Text(
              'Unable to read download usage',
              style: AppTypography.body.copyWith(color: AppColors.muted),
            ),
            data: (bytes) => Row(
              crossAxisAlignment: CrossAxisAlignment.baseline,
              textBaseline: TextBaseline.alphabetic,
              children: [
                Text(formatDownloadBytes(bytes), style: AppTypography.h3),
                const SizedBox(width: AppSpacing.xs),
                Text(
                  cap.bytes == null ? 'used' : 'of ${cap.label} used',
                  style: AppTypography.bodySm.copyWith(color: AppColors.muted),
                ),
              ],
            ),
          ),
          const SizedBox(height: AppSpacing.lg),
          Text('Storage cap', style: AppTypography.labelLg),
          const SizedBox(height: AppSpacing.xs),
          Wrap(
            spacing: AppSpacing.sm,
            runSpacing: AppSpacing.sm,
            children: [
              for (final option in StorageCap.values)
                ChoiceChip(
                  key: Key('storage-cap-${option.name}'),
                  label: Text(option.label),
                  selected: cap == option,
                  onSelected: (_) =>
                      ref.read(storageCapProvider.notifier).setCap(option),
                ),
            ],
          ),
          const SizedBox(height: AppSpacing.md),
          Text('Auto-delete after reading', style: AppTypography.labelLg),
          const SizedBox(height: AppSpacing.xs),
          Text(
            'Finishing a chapter starts a timer; the phone copy is removed '
            'once it elapses (checked on app open, never in the background).',
            style: AppTypography.caption.copyWith(color: AppColors.muted),
          ),
          const SizedBox(height: AppSpacing.xs),
          Consumer(
            builder: (context, ref, _) {
              final interval = ref.watch(retentionIntervalProvider);
              return Wrap(
                spacing: AppSpacing.sm,
                runSpacing: AppSpacing.sm,
                children: [
                  for (final option in RetentionInterval.values)
                    ChoiceChip(
                      key: Key('retention-interval-${option.name}'),
                      label: Text(option.label),
                      selected: interval == option,
                      onSelected: (_) => ref
                          .read(retentionIntervalProvider.notifier)
                          .setInterval(option),
                    ),
                ],
              );
            },
          ),
          const SizedBox(height: AppSpacing.lg),
          if (isIOS)
            const _ManageInFilesNotice()
          else
            Text(
              'Files live in the app\'s private storage. A folder picker for '
              'Android is planned but not in this build.',
              style: AppTypography.caption.copyWith(color: AppColors.muted),
            ),
          const SizedBox(height: AppSpacing.lg),
          breakdownAsync.when(
            loading: () => const SkeletonBox(width: double.infinity, height: 60),
            error: (_, __) => const SizedBox.shrink(),
            data: (series) {
              if (series.isEmpty) return const SizedBox.shrink();
              return Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('By series', style: AppTypography.labelLg),
                  const SizedBox(height: AppSpacing.xs),
                  for (final entry in series)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: AppSpacing.xxs),
                      child: Row(
                        children: [
                          if (entry.anyPinned) ...[
                            const Icon(Icons.push_pin, size: 14, color: AppColors.primary),
                            const SizedBox(width: AppSpacing.xxs),
                          ],
                          Expanded(
                            child: Text(
                              entry.seriesTitle?.isNotEmpty ?? false
                                  ? entry.seriesTitle!
                                  : entry.seriesKey,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: AppTypography.bodySm,
                            ),
                          ),
                          const SizedBox(width: AppSpacing.sm),
                          Text(
                            '${entry.chapterCount} ch · ${formatDownloadBytes(entry.bytes)}',
                            style: AppTypography.caption.copyWith(color: AppColors.muted),
                          ),
                        ],
                      ),
                    ),
                  const SizedBox(height: AppSpacing.md),
                ],
              );
            },
          ),
          OutlinedButton(
            key: const Key('free-up-space'),
            onPressed: () => _freeUpSpace(context, ref),
            child: const Text('Free up space'),
          ),
        ],
      ),
    );
  }

  Future<void> _freeUpSpace(BuildContext context, WidgetRef ref) async {
    final removed = await ref.read(downloadsStorageActionsProvider).freeUpSpace();
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          removed == 0
              ? 'Nothing to free up right now.'
              : removed == 1
                  ? 'Removed 1 chapter.'
                  : 'Removed $removed chapters.',
        ),
      ),
    );
  }
}

class _ManageInFilesNotice extends StatelessWidget {
  const _ManageInFilesNotice();

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.fg.withAlpha(13),
        borderRadius: BorderRadius.circular(AppRadius.md),
        border: Border.all(color: AppColors.border),
      ),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Row(
          children: [
            const Icon(Icons.folder_open_outlined, color: AppColors.muted, size: 18),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Text(
                'Browse, copy or delete downloaded chapters from the Files '
                'app: On My iPhone → ManhwaManiacs.',
                style: AppTypography.caption.copyWith(color: AppColors.muted),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
