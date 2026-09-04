import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/features/library/models/library_query.dart';

class SearchToolbar extends StatefulWidget {
  const SearchToolbar({
    super.key,
    required this.query,
    required this.resultCount,
    required this.isSearching,
    required this.onSearchChanged,
    required this.onFilterChanged,
    required this.onFavoritesChanged,
    required this.onSortChanged,
    required this.onViewModeChanged,
    this.searchController,
  });

  final LibraryQuery query;
  final int resultCount;
  final bool isSearching;
  final ValueChanged<String> onSearchChanged;
  final ValueChanged<LibraryFilter> onFilterChanged;
  final ValueChanged<bool> onFavoritesChanged;
  final ValueChanged<LibrarySort> onSortChanged;
  final ValueChanged<LibraryViewMode> onViewModeChanged;
  final TextEditingController? searchController;

  @override
  State<SearchToolbar> createState() => _SearchToolbarState();
}

class _SearchToolbarState extends State<SearchToolbar> {
  late final TextEditingController _controller;
  late final bool _ownsController;

  @override
  void initState() {
    super.initState();
    _ownsController = widget.searchController == null;
    _controller = widget.searchController ??
        TextEditingController(text: widget.query.search);
  }

  @override
  void didUpdateWidget(SearchToolbar oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.query.search != oldWidget.query.search &&
        widget.query.search != _controller.text) {
      _controller.text = widget.query.search;
    }
  }

  @override
  void dispose() {
    if (_ownsController) _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'Search',
          style: AppTypography.displayMd,
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: AppSpacing.sm),
        Text(
          'Find your next favorite series',
          style: AppTypography.body.copyWith(color: context.colors.muted),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: AppSpacing.xl2),
        TextField(
          controller: _controller,
          onChanged: widget.onSearchChanged,
          textInputAction: TextInputAction.search,
          decoration: InputDecoration(
            prefixIcon: Icon(Icons.search, color: context.colors.muted),
            hintText: 'Search manga, manhwa, webtoons...',
            filled: true,
            fillColor: context.colors.fg.withAlpha(8),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(AppRadius.xl),
              borderSide: BorderSide(color: context.colors.border.withAlpha(128)),
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(AppRadius.xl),
              borderSide: BorderSide(color: context.colors.border.withAlpha(128)),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(AppRadius.xl),
              borderSide: BorderSide(color: context.colors.primary.withAlpha(77)),
            ),
            contentPadding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.xl2,
              vertical: AppSpacing.lg,
            ),
          ),
        ),
        if (widget.isSearching) ...[
          const SizedBox(height: AppSpacing.xl2),
          Row(
            children: [
              Expanded(
                child: Text(
                  widget.isSearching && widget.resultCount == 0
                      ? 'Searching…'
                      : '${widget.resultCount} ${widget.resultCount == 1 ? 'result' : 'results'} found',
                  style: AppTypography.body.copyWith(color: context.colors.muted),
                ),
              ),
              _ViewModeToggle(
                viewMode: widget.query.viewMode,
                onChanged: widget.onViewModeChanged,
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.lg),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: [
                for (final filter in LibraryFilter.values)
                  Padding(
                    padding: const EdgeInsets.only(right: AppSpacing.sm),
                    child: FilterChip(
                      label: Text(filter.label),
                      selected: widget.query.filter == filter &&
                          !widget.query.favoritesOnly,
                      onSelected: (_) {
                        widget.onFilterChanged(filter);
                        if (widget.query.favoritesOnly) {
                          widget.onFavoritesChanged(false);
                        }
                      },
                      selectedColor: context.colors.primary,
                      labelStyle: AppTypography.label.copyWith(
                        color: widget.query.filter == filter &&
                                !widget.query.favoritesOnly
                            ? context.colors.primaryFg
                            : context.colors.muted,
                      ),
                      backgroundColor: context.colors.fg.withAlpha(13),
                      side: BorderSide(color: context.colors.border.withAlpha(128)),
                      showCheckmark: false,
                    ),
                  ),
                FilterChip(
                  label: const Text('★ Favorites'),
                  selected: widget.query.favoritesOnly,
                  onSelected: (_) =>
                      widget.onFavoritesChanged(!widget.query.favoritesOnly),
                  selectedColor: context.colors.warning.withAlpha(51),
                  labelStyle: AppTypography.label.copyWith(
                    color: widget.query.favoritesOnly
                        ? context.colors.warning
                        : context.colors.muted,
                  ),
                  backgroundColor: context.colors.fg.withAlpha(13),
                  side: BorderSide(color: context.colors.border.withAlpha(128)),
                  showCheckmark: false,
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
