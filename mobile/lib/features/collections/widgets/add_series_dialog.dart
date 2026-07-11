import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/collections/providers/collection_detail_provider.dart';
import 'package:manhwamaniacs/features/library/utils/cover_url.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/widgets/series_cover_image.dart';

class AddSeriesDialog extends ConsumerStatefulWidget {
  const AddSeriesDialog({
    super.key,
    required this.existingSeriesIds,
    required this.onAdd,
  });

  final Set<int> existingSeriesIds;
  final Future<AppError?> Function(int seriesId) onAdd;

  @override
  ConsumerState<AddSeriesDialog> createState() => _AddSeriesDialogState();
}

class _AddSeriesDialogState extends ConsumerState<AddSeriesDialog> {
  final _searchController = TextEditingController();
  var _submitting = false;

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _addSeries(int seriesId) async {
    if (_submitting) return;
    setState(() => _submitting = true);
    final error = await widget.onAdd(seriesId);
    if (!mounted) return;
    setState(() => _submitting = false);
    if (error == null) Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    final pickerAsync = ref.watch(librarySeriesPickerProvider);
    final query = _searchController.text.trim().toLowerCase();

    return AlertDialog(
      title: const Text('Add Series to Collection'),
      content: SizedBox(
        width: double.maxFinite,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: _searchController,
              decoration: const InputDecoration(
                prefixIcon: Icon(Icons.search),
                hintText: 'Search series…',
              ),
              onChanged: (_) => setState(() {}),
            ),
            const SizedBox(height: AppSpacing.lg),
            SizedBox(
              height: 320,
              child: pickerAsync.when(
                loading: () => const Center(child: CircularProgressIndicator()),
                error: (error, _) => Center(
                  child: Text(
                    error is AppError ? error.userMessage : 'Failed to load series.',
                    style: AppTypography.body.copyWith(color: AppColors.danger),
                    textAlign: TextAlign.center,
                  ),
                ),
                data: (allSeries) {
                  final available = allSeries
                      .where((series) => !widget.existingSeriesIds.contains(series.id))
                      .where(
                        (series) =>
                            query.isEmpty ||
                            series.title.toLowerCase().contains(query) ||
                            (series.author?.toLowerCase().contains(query) ?? false),
                      )
                      .toList();

                  if (available.isEmpty) {
                    return Center(
                      child: Text(
                        query.isEmpty ? 'No series available.' : 'No series match your search.',
                        style: AppTypography.body.copyWith(color: AppColors.muted),
                        textAlign: TextAlign.center,
                      ),
                    );
                  }

                  final baseUrl = ref.watch(apiBaseUrlProvider);
                  return ListView.separated(
                    itemCount: available.length,
                    separatorBuilder: (_, __) => const SizedBox(height: AppSpacing.sm),
                    itemBuilder: (context, index) {
                      final series = available[index];
                      return Material(
                        color: AppColors.panel,
                        borderRadius: BorderRadius.circular(12),
                        child: InkWell(
                          onTap: _submitting ? null : () => _addSeries(series.id),
                          borderRadius: BorderRadius.circular(12),
                          child: Padding(
                            padding: const EdgeInsets.all(AppSpacing.md),
                            child: Row(
                              children: [
                                SizedBox(
                                  width: 36,
                                  height: 54,
                                  child: SeriesCoverImage(
                                    url: seriesCoverUrl(baseUrl, series.id),
                                    borderRadius: 8,
                                  ),
                                ),
                                const SizedBox(width: AppSpacing.md),
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                        series.title,
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                        style: AppTypography.labelLg,
                                      ),
                                      if (series.author != null &&
                                          series.author!.isNotEmpty)
                                        Text(
                                          series.author!,
                                          maxLines: 1,
                                          overflow: TextOverflow.ellipsis,
                                          style: AppTypography.caption.copyWith(
                                            color: AppColors.muted,
                                          ),
                                        ),
                                    ],
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      );
                    },
                  );
                },
              ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: _submitting ? null : () => Navigator.of(context).pop(),
          child: const Text('Close'),
        ),
      ],
    );
  }
}