import 'package:aistudio_mobile/app/theme/app_colors.dart';
import 'package:aistudio_mobile/app/theme/app_radius.dart';
import 'package:aistudio_mobile/app/theme/app_spacing.dart';
import 'package:aistudio_mobile/app/theme/app_typography.dart';
import 'package:aistudio_mobile/features/downloads/models/download_item.dart';
import 'package:aistudio_mobile/features/downloads/models/download_metrics.dart';
import 'package:aistudio_mobile/features/downloads/models/series_download_group.dart';
import 'package:aistudio_mobile/features/downloads/utils/download_formatters.dart';
import 'package:aistudio_mobile/features/downloads/utils/download_grouping.dart';
import 'package:aistudio_mobile/features/downloads/utils/download_queue_status.dart';
import 'package:aistudio_mobile/shared/widgets/glass_card.dart';
import 'package:flutter/material.dart';

class DownloadsMetricsPanel extends StatelessWidget {
  const DownloadsMetricsPanel({super.key, required this.metrics});

  final DownloadMetrics metrics;

  @override
  Widget build(BuildContext context) {
    final overallPercent = metrics.total > 0
        ? ((metrics.completed / metrics.total) * 100).round()
        : 0;

    return GlassCard(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(AppRadius.lg),
                  gradient: LinearGradient(
                    colors: [
                      AppColors.primary.withAlpha(51),
                      AppColors.cyan400.withAlpha(26),
                    ],
                  ),
                ),
                child: const Icon(Icons.download, color: AppColors.violet400),
              ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Overall Progress', style: AppTypography.labelLg),
                    Text(
                      '${metrics.active} downloading, ${metrics.queued} queued'
                      '${metrics.paused > 0 ? ', ${metrics.paused} paused' : ''}',
                      style: AppTypography.bodySm.copyWith(color: AppColors.muted),
                    ),
                  ],
                ),
              ),
              Text(
                '$overallPercent%',
                style: AppTypography.h3.copyWith(color: AppColors.cyan400),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.lg),
          ClipRRect(
            borderRadius: BorderRadius.circular(AppRadius.full),
            child: LinearProgressIndicator(
              value: overallPercent / 100,
              minHeight: 8,
              backgroundColor: AppColors.fg.withAlpha(13),
              valueColor: const AlwaysStoppedAnimation<Color>(AppColors.primary),
            ),
          ),
          const SizedBox(height: AppSpacing.lg),
          Wrap(
            spacing: AppSpacing.sm,
            runSpacing: AppSpacing.sm,
            children: [
              _StatTile(label: 'Active', value: '${metrics.active}'),
              _StatTile(label: 'Queued', value: '${metrics.queued}'),
              _StatTile(label: 'Completed', value: '${metrics.completed}'),
              _StatTile(label: 'Failed', value: '${metrics.failed}'),
              _StatTile(
                label: 'Speed',
                value: formatDownloadSpeed(
                  metrics.overallSpeedBps,
                  metrics.overallSpeedMbps,
                ),
              ),
              _StatTile(
                label: 'ETA',
                value: formatDownloadEta(metrics.overallEtaSeconds),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _StatTile extends StatelessWidget {
  const _StatTile({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.sm,
      ),
      decoration: BoxDecoration(
        color: AppColors.fg.withAlpha(8),
        borderRadius: BorderRadius.circular(AppRadius.lg),
        border: Border.all(color: AppColors.border.withAlpha(128)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: AppTypography.caption),
          Text(value, style: AppTypography.labelLg),
        ],
      ),
    );
  }
}

class DownloadFilterChips extends StatelessWidget {
  const DownloadFilterChips({
    super.key,
    required this.items,
    required this.activeFilter,
    required this.onChanged,
  });

  final List<DownloadItem> items;
  final DownloadFilterTab activeFilter;
  final ValueChanged<DownloadFilterTab> onChanged;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: DownloadFilterTab.values.map((filter) {
          final count = downloadFilterCount(items, filter);
          final selected = activeFilter == filter;
          return Padding(
            padding: const EdgeInsets.only(right: AppSpacing.sm),
            child: FilterChip(
              label: Text('${filter.label} ($count)'),
              selected: selected,
              onSelected: (_) => onChanged(filter),
              selectedColor: AppColors.primary,
              labelStyle: AppTypography.label.copyWith(
                color: selected ? AppColors.primaryFg : AppColors.muted,
              ),
              backgroundColor: AppColors.fg.withAlpha(13),
              side: BorderSide(color: AppColors.border.withAlpha(128)),
              showCheckmark: false,
            ),
          );
        }).toList(),
      ),
    );
  }
}

class DownloadThumbnail extends StatelessWidget {
  const DownloadThumbnail({super.key, required this.title});

  final String title;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 56,
      height: 56,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(AppRadius.lg),
        gradient: LinearGradient(
          colors: [
            AppColors.primary.withAlpha(77),
            AppColors.cyan400.withAlpha(51),
          ],
        ),
        border: Border.all(color: AppColors.fg.withAlpha(26)),
      ),
      child: Text(
        seriesInitials(title),
        style: AppTypography.labelLg.copyWith(
          color: Colors.white.withAlpha(230),
          letterSpacing: 1.2,
        ),
      ),
    );
  }
}

class DownloadRow extends StatelessWidget {
  const DownloadRow({
    super.key,
    required this.item,
    required this.busy,
    required this.onPause,
    required this.onResume,
    required this.onCancel,
    required this.onRetry,
  });

  final DownloadItem item;
  final bool busy;
  final VoidCallback onPause;
  final VoidCallback onResume;
  final VoidCallback onCancel;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final actions = downloadRowActions(item);
    final displayStatus = downloadQueueDisplayStatus(item);

    return GlassCard(
      key: Key('download-row-${item.id}'),
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          DownloadThumbnail(title: item.seriesTitle),
          const SizedBox(width: AppSpacing.lg),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            item.seriesTitle,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: AppTypography.labelLg,
                          ),
                          Text(
                            item.chapterTitle,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: AppTypography.bodySm.copyWith(color: AppColors.muted),
                          ),
                        ],
                      ),
                    ),
                    _StatusBadge(item: item),
                  ],
                ),
                const SizedBox(height: AppSpacing.md),
                ClipRRect(
                  borderRadius: BorderRadius.circular(AppRadius.full),
                  child: LinearProgressIndicator(
                    value: (item.progress / 100).clamp(0, 1),
                    minHeight: 6,
                    backgroundColor: AppColors.fg.withAlpha(13),
                    valueColor: const AlwaysStoppedAnimation<Color>(AppColors.primary),
                  ),
                ),
                const SizedBox(height: AppSpacing.sm),
                Wrap(
                  spacing: AppSpacing.md,
                  runSpacing: AppSpacing.xs,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    Text(
                      '${item.pagesDone}/${item.pagesTotal > 0 ? item.pagesTotal : '?'} pages',
                      style: AppTypography.caption,
                    ),
                    if (displayStatus == DownloadQueueDisplayStatus.downloading)
                      Text(
                        formatDownloadSpeed(item.speedBps, item.speedMbps),
                        style: AppTypography.caption.copyWith(color: AppColors.cyan400),
                      ),
                    if (displayStatus == DownloadQueueDisplayStatus.downloading &&
                        item.etaSeconds != null &&
                        item.etaSeconds! > 0)
                      Text(
                        'ETA ${formatDownloadEta(item.etaSeconds)}',
                        style: AppTypography.caption,
                      ),
                    Text(
                      '${item.progress.round()}%',
                      style: AppTypography.caption.copyWith(fontWeight: FontWeight.w600),
                    ),
                    Text(
                      formatDownloadBytes(item.bytesDownloaded),
                      style: AppTypography.caption,
                    ),
                  ],
                ),
                if (item.error != null) ...[
                  const SizedBox(height: AppSpacing.sm),
                  Text(
                    item.error!,
                    style: AppTypography.bodySm.copyWith(color: AppColors.danger),
                  ),
                ],
                if (item.retryCount > 0) ...[
                  const SizedBox(height: AppSpacing.xs),
                  Text(
                    'Retries: ${item.retryCount}',
                    style: AppTypography.caption,
                  ),
                ],
                const SizedBox(height: AppSpacing.md),
                Wrap(
                  spacing: AppSpacing.sm,
                  children: [
                    if (actions.showPause)
                      OutlinedButton.icon(
                        key: Key('download-pause-${item.id}'),
                        onPressed: busy ? null : onPause,
                        icon: const Icon(Icons.pause, size: 16),
                        label: const Text('Pause'),
                      ),
                    if (actions.showResume)
                      OutlinedButton.icon(
                        key: Key('download-resume-${item.id}'),
                        onPressed: busy ? null : onResume,
                        icon: const Icon(Icons.play_arrow, size: 16),
                        label: const Text('Resume'),
                      ),
                    if (actions.showRetry)
                      OutlinedButton.icon(
                        key: Key('download-retry-${item.id}'),
                        onPressed: busy ? null : onRetry,
                        icon: const Icon(Icons.refresh, size: 16),
                        label: const Text('Retry'),
                      ),
                    if (actions.showCancel)
                      TextButton.icon(
                        key: Key('download-cancel-${item.id}'),
                        onPressed: busy ? null : onCancel,
                        icon: const Icon(Icons.close, size: 16),
                        label: const Text('Cancel'),
                        style: TextButton.styleFrom(foregroundColor: AppColors.danger),
                      ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class CompletedDownloadRow extends StatelessWidget {
  const CompletedDownloadRow({
    super.key,
    required this.item,
    this.onTap,
  });

  final DownloadItem item;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        key: Key('completed-download-${item.id}'),
        onTap: onTap,
        borderRadius: BorderRadius.circular(AppRadius.xl),
        child: Container(
          padding: const EdgeInsets.all(AppSpacing.lg),
          decoration: BoxDecoration(
            color: AppColors.fg.withAlpha(5),
            borderRadius: BorderRadius.circular(AppRadius.xl),
            border: Border.all(color: AppColors.border.withAlpha(77)),
          ),
          child: Row(
            children: [
              DownloadThumbnail(title: item.seriesTitle),
              const SizedBox(width: AppSpacing.lg),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(item.seriesTitle, style: AppTypography.labelLg),
                    Text(
                      '${item.chapterTitle} · ${formatDownloadBytes(item.bytesDownloaded)}',
                      style: AppTypography.bodySm.copyWith(color: AppColors.muted),
                    ),
                  ],
                ),
              ),
              const Icon(Icons.check_circle, color: AppColors.success),
            ],
          ),
        ),
      ),
    );
  }
}

class SeriesGroupCard extends StatefulWidget {
  const SeriesGroupCard({
    super.key,
    required this.group,
    required this.filter,
    required this.busy,
    required this.onPauseSeries,
    required this.onResumeSeries,
    required this.onCancelSeries,
    required this.onPauseItem,
    required this.onResumeItem,
    required this.onCancelItem,
    required this.onRetryItem,
  });

  final SeriesDownloadGroup group;
  final DownloadFilterTab filter;
  final bool busy;
  final VoidCallback onPauseSeries;
  final VoidCallback onResumeSeries;
  final VoidCallback onCancelSeries;
  final ValueChanged<int> onPauseItem;
  final ValueChanged<int> onResumeItem;
  final ValueChanged<int> onCancelItem;
  final ValueChanged<int> onRetryItem;

  @override
  State<SeriesGroupCard> createState() => _SeriesGroupCardState();
}

class _SeriesGroupCardState extends State<SeriesGroupCard> {
  var _expanded = true;

  @override
  Widget build(BuildContext context) {
    final rows = visibleGroupItems(widget.group)
        .where((item) => matchesDownloadFilter(item, widget.filter))
        .toList();
    if (rows.isEmpty) return const SizedBox.shrink();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        GlassCard(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              InkWell(
                onTap: () => setState(() => _expanded = !_expanded),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        widget.group.seriesTitle,
                        style: AppTypography.labelLg.copyWith(
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                    Icon(
                      _expanded ? Icons.expand_less : Icons.expand_more,
                      color: AppColors.muted,
                    ),
                  ],
                ),
              ),
              const SizedBox(height: AppSpacing.xs),
              Text(
                '${widget.group.source} · ${rows.length} chapter${rows.length == 1 ? '' : 's'} in queue',
                style: AppTypography.caption,
              ),
              const SizedBox(height: AppSpacing.sm),
              Wrap(
                spacing: AppSpacing.sm,
                runSpacing: AppSpacing.xs,
                children: [
                  if (widget.group.active > 0)
                    _GroupBadge('${widget.group.active} downloading'),
                  if (widget.group.queued > 0)
                    _GroupBadge('${widget.group.queued} queued', cyan: true),
                  if (widget.group.paused > 0)
                    _GroupBadge('${widget.group.paused} paused', amber: true),
                  if (widget.group.failed > 0)
                    _GroupBadge('${widget.group.failed} failed', danger: true),
                ],
              ),
              const SizedBox(height: AppSpacing.md),
              Wrap(
                spacing: AppSpacing.sm,
                runSpacing: AppSpacing.sm,
                children: [
                  OutlinedButton(
                    onPressed: widget.busy || !seriesCanPause(widget.group)
                        ? null
                        : widget.onPauseSeries,
                    child: const Text('Pause Series'),
                  ),
                  OutlinedButton(
                    onPressed: widget.busy || !seriesCanResume(widget.group)
                        ? null
                        : widget.onResumeSeries,
                    child: const Text('Resume Series'),
                  ),
                  TextButton(
                    onPressed: widget.busy || !seriesCanCancel(widget.group)
                        ? null
                        : widget.onCancelSeries,
                    style: TextButton.styleFrom(foregroundColor: AppColors.danger),
                    child: const Text('Cancel Series'),
                  ),
                ],
              ),
            ],
          ),
        ),
        if (_expanded) ...[
          const SizedBox(height: AppSpacing.md),
          for (final item in rows) ...[
            DownloadRow(
              item: item,
              busy: widget.busy,
              onPause: () => widget.onPauseItem(item.id),
              onResume: () => widget.onResumeItem(item.id),
              onCancel: () => widget.onCancelItem(item.id),
              onRetry: () => widget.onRetryItem(item.id),
            ),
            const SizedBox(height: AppSpacing.md),
          ],
        ],
      ],
    );
  }
}

class _GroupBadge extends StatelessWidget {
  const _GroupBadge(this.label, {this.cyan = false, this.amber = false, this.danger = false});

  final String label;
  final bool cyan;
  final bool amber;
  final bool danger;

  @override
  Widget build(BuildContext context) {
    final color = danger
        ? AppColors.danger
        : amber
            ? AppColors.warning
            : cyan
                ? AppColors.cyan400
                : AppColors.primary;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: color.withAlpha(38),
        borderRadius: BorderRadius.circular(AppRadius.sm),
        border: Border.all(color: color.withAlpha(102)),
      ),
      child: Text(
        label,
        style: AppTypography.caption.copyWith(color: color),
      ),
    );
  }
}

class _StatusBadge extends StatelessWidget {
  const _StatusBadge({required this.item});

  final DownloadItem item;

  @override
  Widget build(BuildContext context) {
    final color = downloadQueueStatusColor(item);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color.withAlpha(38),
        borderRadius: BorderRadius.circular(AppRadius.full),
        border: Border.all(color: color.withAlpha(102)),
      ),
      child: Text(
        downloadQueueStatusLabel(item),
        style: AppTypography.caption.copyWith(color: color),
      ),
    );
  }
}

class DownloadQueueSummary extends StatelessWidget {
  const DownloadQueueSummary({super.key, required this.items});

  final List<DownloadItem> items;

  @override
  Widget build(BuildContext context) {
    final counts = countDownloadQueueStatuses(items);
    final entries = <(String, int)>[
      ('Queued', counts[DownloadQueueDisplayStatus.queued]!),
      ('Downloading', counts[DownloadQueueDisplayStatus.downloading]!),
      ('Verifying', counts[DownloadQueueDisplayStatus.verifying]!),
      ('Importing', counts[DownloadQueueDisplayStatus.importing]!),
      ('Completed', counts[DownloadQueueDisplayStatus.completed]!),
      ('Failed', counts[DownloadQueueDisplayStatus.failed]!),
      ('Paused', counts[DownloadQueueDisplayStatus.paused]!),
    ].where((entry) => entry.$2 > 0).toList();

    if (entries.isEmpty) return const SizedBox.shrink();

    return Wrap(
      spacing: AppSpacing.sm,
      runSpacing: AppSpacing.sm,
      children: [
        for (final entry in entries)
          Container(
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.md,
              vertical: AppSpacing.sm,
            ),
            decoration: BoxDecoration(
              color: AppColors.fg.withAlpha(8),
              borderRadius: BorderRadius.circular(AppRadius.lg),
              border: Border.all(color: AppColors.border.withAlpha(128)),
            ),
            child: Text(
              '${entry.$1}: ${entry.$2}',
              style: AppTypography.caption,
            ),
          ),
      ],
    );
  }
}

class DownloadsEmptyPanel extends StatelessWidget {
  const DownloadsEmptyPanel({super.key, required this.message, required this.subtitle});

  final String message;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(AppSpacing.xl4),
      decoration: BoxDecoration(
        color: AppColors.panel,
        borderRadius: BorderRadius.circular(AppRadius.xl),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        children: [
          Icon(Icons.download_outlined, size: 36, color: AppColors.muted.withAlpha(102)),
          const SizedBox(height: AppSpacing.md),
          Text(message, style: AppTypography.h4, textAlign: TextAlign.center),
          const SizedBox(height: AppSpacing.sm),
          Text(
            subtitle,
            style: AppTypography.body.copyWith(color: AppColors.muted),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }
}
