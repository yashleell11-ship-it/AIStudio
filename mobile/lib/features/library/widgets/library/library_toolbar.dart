import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/features/library/models/library_query.dart';

class LibraryToolbar extends StatefulWidget {
  const LibraryToolbar({
    super.key,
    required this.query,
    required this.seriesCount,
    required this.onSearchChanged,
    required this.onSortChanged,
    required this.onFilterChanged,
    required this.onViewModeChanged,
    this.coverScale,
    this.onCoverScaleChanged,
  });

  final LibraryQuery query;
  final int seriesCount;
  final ValueChanged<String> onSearchChanged;
  final ValueChanged<LibrarySort> onSortChanged;
  final ValueChanged<LibraryFilter> onFilterChanged;
  final ValueChanged<LibraryViewMode> onViewModeChanged;

  /// When provided (grid mode), shows a cover-size slider.
  final double? coverScale;
  final ValueChanged<double>? onCoverScaleChanged;

  @override
  State<LibraryToolbar> createState() => _LibraryToolbarState();
}

class _LibraryToolbarState extends State<LibraryToolbar> {
  late final TextEditingController _searchController;

  @override
  void initState() {
    super.initState();
    _searchController = TextEditingController(text: widget.query.search);
  }

  @override
  void didUpdateWidget(LibraryToolbar oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.query.search != oldWidget.query.search &&
        widget.query.search != _searchController.text) {
      _searchController.text = widget.query.search;
    }
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final countLabel = widget.seriesCount.toString();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Library', style: AppTypography.h1),
                  const SizedBox(height: AppSpacing.xs),
                  Text(
                    '$countLabel ${widget.seriesCount == 1 ? 'series' : 'series'}',
                    style: AppTypography.body.copyWith(color: context.colors.muted),
                  ),
                ],
              ),
            ),
            _ViewModeToggle(
              viewMode: widget.query.viewMode,
              onChanged: widget.onViewModeChanged,
            ),
          ],
        ),
        const SizedBox(height: AppSpacing.xl2),
        TextField(
          controller: _searchController,
          onChanged: widget.onSearchChanged,
          decoration: InputDecoration(
            prefixIcon: Icon(Icons.search, color: context.colors.muted),
            hintText: 'Search by title, author, or tag...',
          ),
        ),
        const SizedBox(height: AppSpacing.lg),
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            children: [
              for (final filter in libraryBrowseFilterOptions)
                Padding(
                  padding: const EdgeInsets.only(right: AppSpacing.sm),
                  child: _FilterChip(
                    label: filter.label,
                    selected: widget.query.filter == filter,
                    onTap: () => widget.onFilterChanged(filter),
                  ),
                ),
            ],
          ),
        ),
        const SizedBox(height: AppSpacing.lg),
        DropdownButtonFormField<LibrarySort>(
          initialValue: widget.query.sort,
          decoration: const InputDecoration(
            labelText: 'Sort',
            isDense: true,
          ),
          items: libraryBrowseSortOptions
              .map(
                (sort) => DropdownMenuItem(
                  value: sort,
                  child: Text(sort.label),
                ),
              )
              .toList(),
          onChanged: (value) {
            if (value != null) widget.onSortChanged(value);
          },
        ),
        if (widget.coverScale != null &&
            widget.onCoverScaleChanged != null &&
            widget.query.viewMode == LibraryViewMode.grid) ...[
          const SizedBox(height: AppSpacing.sm),
          Row(
            children: [
              Icon(
                Icons.photo_size_select_small,
                size: 18,
                color: context.colors.muted,
              ),
              Expanded(
                child: Slider(
                  value: widget.coverScale!,
                  min: 0.7,
                  max: 1.6,
                  onChanged: widget.onCoverScaleChanged,
                ),
              ),
              Icon(
                Icons.photo_size_select_large,
                size: 18,
                color: context.colors.muted,
              ),
            ],
          ),
        ],
      ],
    );
  }
}

class _ViewModeToggle extends StatelessWidget {
  const _ViewModeToggle({
    required this.viewMode,
    required this.onChanged,
  });

  final LibraryViewMode viewMode;
  final ValueChanged<LibraryViewMode> onChanged;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: context.colors.fg.withAlpha(13),
        borderRadius: BorderRadius.circular(AppRadius.md),
        border: Border.all(color: context.colors.border.withAlpha(128)),
      ),
      padding: const EdgeInsets.all(2),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _ModeButton(
            icon: Icons.grid_view,
            selected: viewMode == LibraryViewMode.grid,
            onTap: () => onChanged(LibraryViewMode.grid),
          ),
          _ModeButton(
            icon: Icons.view_list,
            selected: viewMode == LibraryViewMode.list,
            onTap: () => onChanged(LibraryViewMode.list),
          ),
        ],
      ),
    );
  }
}

class _ModeButton extends StatelessWidget {
  const _ModeButton({
    required this.icon,
    required this.selected,
    required this.onTap,
  });

  final IconData icon;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: selected ? context.colors.primary : Colors.transparent,
      borderRadius: BorderRadius.circular(AppRadius.sm),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(AppRadius.sm),
        child: SizedBox(
          width: 32,
          height: 32,
          child: Icon(
            icon,
            size: 18,
            color: selected ? context.colors.primaryFg : context.colors.muted,
          ),
        ),
      ),
    );
  }
}

class _FilterChip extends StatelessWidget {
  const _FilterChip({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return FilterChip(
      label: Text(label),
      selected: selected,
      onSelected: (_) => onTap(),
      selectedColor: context.colors.primary,
      checkmarkColor: context.colors.primaryFg,
      labelStyle: AppTypography.label.copyWith(
        color: selected ? context.colors.primaryFg : context.colors.muted,
      ),
      backgroundColor: context.colors.fg.withAlpha(13),
      side: BorderSide(color: context.colors.border.withAlpha(128)),
      showCheckmark: false,
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm),
    );
  }
}
