import 'package:aistudio_mobile/app/theme/app_colors.dart';
import 'package:aistudio_mobile/app/theme/app_spacing.dart';
import 'package:aistudio_mobile/app/theme/app_typography.dart';
import 'package:aistudio_mobile/features/library/utils/recent_searches.dart';
import 'package:flutter/material.dart';

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
          const SizedBox(height: AppSpacing.md),
          Wrap(
            spacing: AppSpacing.sm,
            runSpacing: AppSpacing.sm,
            children: [
              for (final term in recentSearches)
                _SuggestionChip(label: term, onSelect: () => onSelect(term)),
            ],
          ),
          const SizedBox(height: AppSpacing.xl2),
        ],
        const _SectionLabel(icon: Icons.trending_up, label: 'Trending'),
        const SizedBox(height: AppSpacing.md),
        Wrap(
          spacing: AppSpacing.sm,
          runSpacing: AppSpacing.sm,
          children: [
            for (final term in trendingSearchSuggestions)
              _SuggestionChip(label: term, onSelect: () => onSelect(term)),
          ],
        ),
        const SizedBox(height: AppSpacing.xl2),
        Center(
          child: OutlinedButton.icon(
            onPressed: onToggleFilters,
            icon: const Icon(Icons.tune, size: 18),
            label: const Text('Advanced Filters'),
            style: OutlinedButton.styleFrom(
              foregroundColor:
                  filtersOpen ? AppColors.violet400 : AppColors.muted,
              side: BorderSide(
                color: filtersOpen
                    ? AppColors.violet400.withAlpha(77)
                    : AppColors.border,
              ),
            ),
          ),
        ),
        if (filtersOpen) ...[
          const SizedBox(height: AppSpacing.lg),
          Container(
            padding: const EdgeInsets.all(AppSpacing.lg),
            decoration: BoxDecoration(
              color: AppColors.panel,
              borderRadius: BorderRadius.circular(AppRadius.lg),
              border: Border.all(color: AppColors.border),
            ),
            child: Text(
              'Search matches titles, authors, and descriptions in your local library. '
              'Use the filter chips below results for status and favorites.',
              style: AppTypography.bodySm.copyWith(color: AppColors.muted),
            ),
          ),
        ],
        const SizedBox(height: AppSpacing.xl2),
        Container(
          padding: const EdgeInsets.all(AppSpacing.xl4),
          decoration: BoxDecoration(
            color: AppColors.panel,
            borderRadius: BorderRadius.circular(AppRadius.xl),
            border: Border.all(color: AppColors.border),
          ),
          child: Column(
            children: [
              Icon(Icons.search, size: 32, color: AppColors.muted.withAlpha(102)),
              const SizedBox(height: AppSpacing.md),
              Text(
                'Start typing to search',
                style: AppTypography.h4,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: AppSpacing.sm),
              Text(
                'Search across titles, authors, and descriptions in your library.',
                style: AppTypography.body.copyWith(color: AppColors.muted),
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
        Icon(icon, size: 14, color: AppColors.cyan400),
        const SizedBox(width: AppSpacing.sm),
        Text(
          label.toUpperCase(),
          style: AppTypography.labelSm.copyWith(
            color: AppColors.muted,
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
      backgroundColor: AppColors.fg.withAlpha(8),
      side: BorderSide(color: AppColors.border.withAlpha(128)),
      labelStyle: AppTypography.body.copyWith(color: AppColors.muted),
    );
  }
}
