import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/features/library/utils/recent_searches.dart';

class SearchSuggestionsPanel extends StatelessWidget {
  const SearchSuggestionsPanel({
    super.key,
    required this.recentSearches,
    required this.onSelect,
    required this.filtersOpen,
    required this.onToggleFilters,
  });

  final List<String> recentSearches;
  final ValueChanged<String> onSelect;
  final bool filtersOpen;
  final VoidCallback onToggleFilters;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (recentSearches.isNotEmpty) ...[
          const _SectionLabel(icon: Icons.history, label: 'Recent'),
          SizedBox(height: context.space.md),
          Wrap(
            spacing: context.space.sm,
            runSpacing: context.space.sm,
            children: [
              for (final term in recentSearches)
                _SuggestionChip(label: term, onSelect: () => onSelect(term)),
            ],
          ),
          SizedBox(height: context.space.xl2),
        ],
        const _SectionLabel(icon: Icons.trending_up, label: 'Trending'),
        SizedBox(height: context.space.md),
        Wrap(
          spacing: context.space.sm,
          runSpacing: context.space.sm,
          children: [
            for (final term in trendingSearchSuggestions)
              _SuggestionChip(label: term, onSelect: () => onSelect(term)),
          ],
        ),
        SizedBox(height: context.space.xl2),
        Center(
          child: OutlinedButton.icon(
            onPressed: onToggleFilters,
            icon: const Icon(Icons.tune, size: 18),
            label: const Text('Advanced Filters'),
            style: OutlinedButton.styleFrom(
              foregroundColor:
                  filtersOpen ? context.colors.violet400 : context.colors.muted,
              side: BorderSide(
                color: filtersOpen
                    ? context.colors.violet400.withAlpha(77)
                    : context.colors.border,
              ),
            ),
          ),
        ),
        if (filtersOpen) ...[
          SizedBox(height: context.space.lg),
          Container(
            padding: EdgeInsets.all(context.space.lg),
            decoration: BoxDecoration(
              color: context.colors.panel,
              borderRadius: BorderRadius.circular(context.radii.lg),
              border: Border.all(color: context.colors.border),
            ),
            child: Text(
              'Search matches titles, authors, and descriptions in your local library. '
              'Use the filter chips below results for status and favorites.',
              style: context.text.bodySm.copyWith(color: context.colors.muted),
            ),
          ),
        ],
        SizedBox(height: context.space.xl2),
        Container(
          padding: EdgeInsets.all(context.space.xl4),
          decoration: BoxDecoration(
            color: context.colors.panel,
            borderRadius: BorderRadius.circular(context.radii.xl),
            border: Border.all(color: context.colors.border),
          ),
          child: Column(
            children: [
              Icon(Icons.search, size: 32, color: context.colors.muted.withAlpha(102)),
              SizedBox(height: context.space.md),
              Text(
                'Start typing to search',
                style: context.text.h4,
                textAlign: TextAlign.center,
              ),
              SizedBox(height: context.space.sm),
              Text(
                'Search across titles, authors, and descriptions in your library.',
                style: context.text.body.copyWith(color: context.colors.muted),
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, size: 14, color: context.colors.cyan400),
        SizedBox(width: context.space.sm),
        Text(
          label.toUpperCase(),
          style: context.text.labelSm.copyWith(
            color: context.colors.muted,
            letterSpacing: 1.5,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    );
  }
}

class _SuggestionChip extends StatelessWidget {
  const _SuggestionChip({required this.label, required this.onSelect});

  final String label;
  final VoidCallback onSelect;

  @override
  Widget build(BuildContext context) {
    return ActionChip(
      label: Text(label),
      onPressed: onSelect,
      backgroundColor: context.colors.fg.withAlpha(8),
      side: BorderSide(color: context.colors.border.withAlpha(128)),
      labelStyle: context.text.body.copyWith(color: context.colors.muted),
    );
  }
}
