import 'package:aistudio_mobile/app/theme/app_colors.dart';
import 'package:aistudio_mobile/app/theme/app_spacing.dart';
import 'package:aistudio_mobile/app/theme/app_typography.dart';
import 'package:aistudio_mobile/features/library/models/library_query.dart';
import 'package:flutter/material.dart';

class LibraryToolbar extends StatefulWidget {
  const LibraryToolbar({
    super.key,
    required this.query,
    required this.seriesCount,
    required this.onSearchChanged,
    required this.onSortChanged,
    required this.onFilterChanged,
    required this.onFavoritesChanged,
    required this.onViewModeChanged,
  });

  final LibraryQuery query;
  final int seriesCount;
  final ValueChanged<String> onSearchChanged;
  final ValueChanged<LibrarySort> onSortChanged;
  final ValueChanged<LibraryFilter> onFilterChanged;
  final ValueChanged<bool> onFavoritesChanged;
  final ValueChanged<LibraryViewMode> onViewModeChanged;

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
                    style: AppTypography.body.copyWith(color: AppColors.muted),
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
          decoration: const InputDecoration(
            prefixIcon: Icon(Icons.search, color: AppColors.muted),
            hintText: 'Search by title, author, or tag...',
          ),
        ),
        const SizedBox(height: AppSpacing.lg),
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            children: [
              for (final filter in LibraryFilter.values)
                Padding(
                  padding: const EdgeInsets.only(right: AppSpacing.sm),
                  child: _FilterChip(
                    label: filter.label,
                    selected:
                        widget.query.filter == filter && !widget.query.favoritesOnly,
                    onTap: () {
                      widget.onFilterChanged(filter);
                      if (widget.query.favoritesOnly) {
                        widget.onFavoritesChanged(false);
                      }
                    },
                  ),
                ),
              _FilterChip(
                label: '★ Favorites',
                selected: widget.query.favoritesOnly,
                selectedColor: AppColors.warning.withAlpha(51),
                selectedTextColor: AppColors.warning,
                onTap: () =>
                    widget.onFavoritesChanged(!widget.query.favoritesOnly),
              ),
            ],
          ),
        ),
        const SizedBox(height: AppSpacing.lg),
        DropdownButtonFormField<LibrarySort>(
          value: widget.query.sort,
          decoration: const InputDecoration(
            labelText: 'Sort',
            isDense: true,
          ),
          items: LibrarySort.values
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
        color: AppColors.fg.withAlpha(13),
        borderRadius: BorderRadius.circular(AppRadius.md),
        border: Border.all(color: AppColors.border.withAlpha(128)),
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
      color: selected ? AppColors.primary : Colors.transparent,
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
            color: selected ? AppColors.primaryFg : AppColors.muted,
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
    this.selectedColor,
    this.selectedTextColor,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;
  final Color? selectedColor;
  final Color? selectedTextColor;

  @override
  Widget build(BuildContext context) {
    return FilterChip(
      label: Text(label),
      selected: selected,
      onSelected: (_) => onTap(),
      selectedColor: selectedColor ?? AppColors.primary,
      checkmarkColor: selectedTextColor ?? AppColors.primaryFg,
      labelStyle: AppTypography.label.copyWith(
        color: selected
            ? (selectedTextColor ?? AppColors.primaryFg)
            : AppColors.muted,
      ),
      backgroundColor: AppColors.fg.withAlpha(13),
      side: BorderSide(color: AppColors.border.withAlpha(128)),
      showCheckmark: false,
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm),
    );
  }
}
