import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
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
      padding: EdgeInsets.all(context.space.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.download_done_outlined, color: context.colors.primary, size: 20),
              SizedBox(width: context.space.sm),
              Text('Downloaded chapters', style: context.text.h4),
            ],
          ),
          SizedBox(height: context.space.xs),
          Text(
            'Chapters saved to this phone for offline reading. Deleting a '
            'chapter here never rewinds your reading progress — it stays on '
            'the server and can be re-downloaded any time.',
            style: context.text.bodySm.copyWith(color: context.colors.muted, height: 1.5),
          ),
          SizedBox(height: context.space.md),
          totalAsync.when(
            loading: () => const SkeletonBox(width: 120, height: 20),
            error: (_, __) => Text(
              'Unable to read download usage',
              style: context.text.body.copyWith(color: context.colors.muted),
            ),
            data: (bytes) => Row(
              crossAxisAlignment: CrossAxisAlignment.baseline,
              textBaseline: TextBaseline.alphabetic,
              children: [
                Text(formatDownloadBytes(bytes), style: context.text.h3),
                SizedBox(width: context.space.xs),
                Text(
                  cap.bytes == null ? 'used' : 'of ${cap.label} used',
                  style: context.text.bodySm.copyWith(color: context.colors.muted),
                ),
              ],
            ),
          ),
          SizedBox(height: context.space.lg),
          Text('Storage cap', style: context.text.labelLg),
          SizedBox(height: context.space.xs),
          Wrap(
            spacing: context.space.sm,
            runSpacing: context.space.sm,
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
          SizedBox(height: context.space.md),
          Text('Auto-delete after reading', style: context.text.labelLg),
          SizedBox(height: context.space.xs),
          Text(
            'Finishing a chapter starts a timer; the phone copy is removed '
            'once it elapses (checked on app open, never in the background).',
            style: context.text.caption.copyWith(color: context.colors.muted),
          ),
          SizedBox(height: context.space.xs),
          Consumer(
            builder: (context, ref, _) {
              final interval = ref.watch(retentionIntervalProvider);
              return Wrap(
                spacing: context.space.sm,
                runSpacing: context.space.sm,
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
          SizedBox(height: context.space.lg),
          if (isIOS)
            const _ManageInFilesNotice()
          else
            Text(
              'Files live in the app\'s private storage. A folder picker for '
              'Android is planned but not in this build.',
              style: context.text.caption.copyWith(color: context.colors.muted),
            ),
          SizedBox(height: context.space.lg),
          breakdownAsync.when(
            loading: () => const SkeletonBox(width: double.infinity, height: 60),
            error: (_, __) => const SizedBox.shrink(),
            data: (series) {
              if (series.isEmpty) return const SizedBox.shrink();
              return Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('By series', style: context.text.labelLg),
                  SizedBox(height: context.space.xs),
                  for (final entry in series)
                    Padding(
                      padding: EdgeInsets.symmetric(vertical: context.space.xxs),
                      child: Row(
                        children: [
                          if (entry.anyPinned) ...[
                            Icon(Icons.push_pin, size: 14, color: context.colors.primary),
                            SizedBox(width: context.space.xxs),
                          ],
                          Expanded(
                            child: Text(
                              entry.seriesTitle?.isNotEmpty ?? false
                                  ? entry.seriesTitle!
                                  : entry.seriesKey,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: context.text.bodySm,
                            ),
                          ),
                          SizedBox(width: context.space.sm),
                          Text(
                            '${entry.chapterCount} ch · ${formatDownloadBytes(entry.bytes)}',
                            style: context.text.caption.copyWith(color: context.colors.muted),
                          ),
                        ],
                      ),
                    ),
                  SizedBox(height: context.space.md),
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
        color: context.colors.fg.withAlpha(13),
        borderRadius: BorderRadius.circular(context.radii.md),
        border: Border.all(color: context.colors.border),
      ),
      child: Padding(
        padding: EdgeInsets.all(context.space.md),
        child: Row(
          children: [
            Icon(Icons.folder_open_outlined, color: context.colors.muted, size: 18),
            SizedBox(width: context.space.sm),
            Expanded(
              child: Text(
                'Browse, copy or delete downloaded chapters from the Files '
                'app: On My iPhone → ManhwaManiacs.',
                style: context.text.caption.copyWith(color: context.colors.muted),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
