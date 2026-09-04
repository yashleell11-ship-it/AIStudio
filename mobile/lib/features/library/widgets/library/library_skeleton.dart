import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
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
          (_) => Padding(
            padding: EdgeInsets.only(bottom: context.space.md),
            child: const SkeletonBox(width: double.infinity, height: 80),
          ),
        ),
      );
    }

    // Must match SeriesGrid exactly, preset bias included, or the page
    // reflows the moment the real data arrives.
    final columns = context.layout.columnsFor(context.seriesGridColumns);

    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: columns,
        crossAxisSpacing: context.space.lg,
        mainAxisSpacing: context.space.lg,
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
      padding: EdgeInsets.all(context.space.xl4),
      decoration: BoxDecoration(
        color: context.colors.panel,
        borderRadius: BorderRadius.circular(context.radii.xl),
        border: Border.all(
          color: context.colors.border,
        ),
      ),
      child: Column(
        children: [
          Text(copy.$1, style: context.text.h4, textAlign: TextAlign.center),
          SizedBox(height: context.space.sm),
          Text(
            copy.$2,
            style: context.text.body.copyWith(color: context.colors.muted),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }
}
