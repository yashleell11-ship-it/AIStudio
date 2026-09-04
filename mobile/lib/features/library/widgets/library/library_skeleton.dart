import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/core/utils/responsive.dart';
import 'package:manhwamaniacs/features/library/models/library_query.dart';
import 'package:manhwamaniacs/shared/widgets/skeleton_box.dart';

class LibrarySkeleton extends StatelessWidget {
  const LibrarySkeleton({
    super.key,
    required this.viewMode,
  });

  final LibraryViewMode viewMode;

  @override
  Widget build(BuildContext context) {
    if (viewMode == LibraryViewMode.list) {
      return Column(
        children: List.generate(
          8,
          (_) => const Padding(
            padding: EdgeInsets.only(bottom: AppSpacing.md),
            child: SkeletonBox(width: double.infinity, height: 80),
          ),
        ),
      );
    }

    final columns = context.seriesGridColumns;

    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: columns,
        crossAxisSpacing: AppSpacing.lg,
        mainAxisSpacing: AppSpacing.lg,
        childAspectRatio: 2 / 3,
      ),
      itemCount: 12,
      itemBuilder: (_, __) => const SkeletonBox(
        width: double.infinity,
        height: double.infinity,
        borderRadius: 16,
      ),
    );
  }
}

class LibraryEmptyPanel extends StatelessWidget {
  const LibraryEmptyPanel({super.key, required this.emptyState});

  final LibraryEmptyState emptyState;

  @override
  Widget build(BuildContext context) {
    final copy = switch (emptyState) {
      LibraryEmptyState.search => (
          'No results found',
          'Try a different search term or clear filters.',
        ),
      LibraryEmptyState.filter => (
          'No series match these filters',
          'Adjust your filters or favorites toggle to see more series.',
        ),
      LibraryEmptyState.library => (
          'Your library is empty',
          'Import a folder containing your manhwa, manga, or manhua collection to get started.',
        ),
    };

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(AppSpacing.xl4),
      decoration: BoxDecoration(
        color: context.colors.panel,
        borderRadius: BorderRadius.circular(AppRadius.xl),
        border: Border.all(
          color: context.colors.border,
        ),
      ),
      child: Column(
        children: [
          Text(copy.$1, style: AppTypography.h4, textAlign: TextAlign.center),
          const SizedBox(height: AppSpacing.sm),
          Text(
            copy.$2,
            style: AppTypography.body.copyWith(color: context.colors.muted),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }
}
