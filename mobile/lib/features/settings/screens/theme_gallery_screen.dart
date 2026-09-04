import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_palette.dart';
import 'package:manhwamaniacs/app/theme/app_palettes.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/app/theme/theme_controller.dart';
import 'package:manhwamaniacs/features/settings/providers/settings_provider.dart';

/// Which half of the registry the gallery is showing.
enum ThemeVariantFilter { all, dark, light }

/// The full theme gallery.
///
/// The Settings pane used to hold the whole registry in one `Wrap`. That was
/// the right shape for fifteen palettes and the wrong one for forty-five: a
/// wall of swatches you scroll past on the way to something else, with no way
/// to ask for the one you are thinking of. So browsing moved here, and what
/// Settings keeps is the flick-through strip.
///
/// Three things make it work at this size:
///
///  * **Search**, pinned under the title, over name, blurb and author — so
///    "gruv", "pastel" and "catppuccin" all land somewhere useful.
///  * **A dark/light filter**, because that is the first cut anyone makes and
///    it halves the list on its own.
///  * **Rows, not a grid.** With forty-five near-cousins the thumbnail alone
///    stops being enough to tell two pastel darks apart; the blurb is what
///    distinguishes them, and a row has space for it.
///
/// Tapping applies immediately — the gallery is drawn in the palette it is
/// picking, so the preview is the whole app, not a tile.
class ThemeGalleryScreen extends ConsumerStatefulWidget {
  const ThemeGalleryScreen({super.key});

  @override
  ConsumerState<ThemeGalleryScreen> createState() => _ThemeGalleryScreenState();
}

class _ThemeGalleryScreenState extends ConsumerState<ThemeGalleryScreen> {
  final TextEditingController _search = TextEditingController();
  ThemeVariantFilter _filter = ThemeVariantFilter.all;
  String _query = '';

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  /// Free-text match over everything a reader might remember about a theme:
  /// its name, the line describing it, and who made it.
  bool _matchesQuery(AppPalette palette) {
    if (_query.isEmpty) return true;
    final query = _query.toLowerCase();
    return palette.name.toLowerCase().contains(query) ||
        palette.description.toLowerCase().contains(query) ||
        palette.author.toLowerCase().contains(query);
  }

  List<AppPalette> _section(List<AppPalette> palettes) =>
      palettes.where(_matchesQuery).toList(growable: false);

  @override
  Widget build(BuildContext context) {
    final active = ref.watch(themeControllerProvider);
    final showDark = _filter != ThemeVariantFilter.light;
    final showLight = _filter != ThemeVariantFilter.dark;
    final darks = showDark ? _section(AppPalettes.darkPalettes) : const <AppPalette>[];
    final lights = showLight ? _section(AppPalettes.lightPalettes) : const <AppPalette>[];
    final empty = darks.isEmpty && lights.isEmpty;

    return Scaffold(
      backgroundColor: context.colors.bg,
      appBar: AppBar(
        backgroundColor: context.colors.surface,
        foregroundColor: context.colors.fg,
        elevation: 0,
        title: const Text('Theme'),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(108),
          child: Padding(
            padding: EdgeInsets.fromLTRB(
              context.space.lg,
              0,
              context.space.lg,
              context.space.sm,
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                _SearchField(
                  controller: _search,
                  onChanged: (value) => setState(() => _query = value.trim()),
                ),
                SizedBox(height: context.space.sm),
                _FilterChips(
                  filter: _filter,
                  onChanged: (value) => setState(() => _filter = value),
                ),
              ],
            ),
          ),
        ),
      ),
      body: CustomScrollView(
        slivers: [
          if (empty)
            SliverFillRemaining(
              hasScrollBody: false,
              child: _NoMatches(query: _query),
            )
          else ...[
            if (darks.isNotEmpty) ..._sliversFor('Dark', darks, active.id),
            if (lights.isNotEmpty) ..._sliversFor('Light', lights, active.id),
            SliverToBoxAdapter(
              child: Padding(
                padding: EdgeInsets.fromLTRB(
                  context.space.lg,
                  context.space.xl,
                  context.space.lg,
                  context.space.xl2,
                ),
                child: Text(
                  'Colour schemes from the base16 community set '
                  '(tinted-theming/schemes), mapped onto this app and checked '
                  'for contrast. The same set the website wears.',
                  style: context.text.labelSm.copyWith(color: context.colors.muted),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  List<Widget> _sliversFor(String label, List<AppPalette> palettes, String activeId) {
    return [
      SliverToBoxAdapter(
        child: Padding(
          padding: EdgeInsets.fromLTRB(
            context.space.lg,
            context.space.lg,
            context.space.lg,
            context.space.sm,
          ),
          child: Row(
            children: [
              Text(
                label.toUpperCase(),
                style: context.text.labelSm.copyWith(
                  color: context.colors.muted,
                  letterSpacing: 1.2,
                ),
              ),
              SizedBox(width: context.space.sm),
              Text(
                '${palettes.length}',
                style: context.text.labelSm.copyWith(
                  color: context.colors.muted.withValues(alpha: 0.6),
                ),
              ),
            ],
          ),
        ),
      ),
      SliverList.builder(
        itemCount: palettes.length,
        itemBuilder: (context, index) {
          final palette = palettes[index];
          return ThemeRow(
            palette: palette,
            selected: palette.id == activeId,
            onTap: () {
              ref.read(hapticsProvider).selection();
              ref.read(themeControllerProvider.notifier).setTheme(palette.id);
            },
          );
        },
      ),
    ];
  }
}

class _SearchField extends StatelessWidget {
  const _SearchField({required this.controller, required this.onChanged});

  final TextEditingController controller;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    return TextField(
      key: const Key('theme-search'),
      controller: controller,
      onChanged: onChanged,
      textInputAction: TextInputAction.search,
      style: context.text.bodySm.copyWith(color: context.colors.fg),
      decoration: InputDecoration(
        isDense: true,
        hintText: 'Search themes',
        hintStyle: context.text.bodySm.copyWith(color: context.colors.muted),
        prefixIcon: Icon(Icons.search, size: 18, color: context.colors.muted),
        filled: true,
        fillColor: context.colors.bg,
        contentPadding: EdgeInsets.symmetric(
          horizontal: context.space.sm,
          vertical: context.space.sm,
        ),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(context.radii.md),
          borderSide: BorderSide(color: context.colors.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(context.radii.md),
          borderSide: BorderSide(color: context.colors.border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(context.radii.md),
          borderSide: BorderSide(color: context.colors.primary),
        ),
      ),
    );
  }
}

class _FilterChips extends StatelessWidget {
  const _FilterChips({required this.filter, required this.onChanged});

  final ThemeVariantFilter filter;
  final ValueChanged<ThemeVariantFilter> onChanged;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        for (final option in ThemeVariantFilter.values) ...[
          if (option != ThemeVariantFilter.values.first)
            SizedBox(width: context.space.xs),
          _Chip(
            label: switch (option) {
              ThemeVariantFilter.all => 'All',
              ThemeVariantFilter.dark => 'Dark',
              ThemeVariantFilter.light => 'Light',
            },
            selected: filter == option,
            onTap: () => onChanged(option),
          ),
        ],
      ],
    );
  }
}

class _Chip extends StatelessWidget {
  const _Chip({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      selected: selected,
      child: GestureDetector(
        key: Key('theme-filter-${label.toLowerCase()}'),
        onTap: onTap,
        child: Container(
          padding: EdgeInsets.symmetric(
            horizontal: context.space.md,
            vertical: context.space.xs,
          ),
          decoration: BoxDecoration(
            color: selected ? context.colors.primary : context.colors.surface,
            borderRadius: BorderRadius.circular(context.radii.xl),
            border: Border.all(
              color: selected ? context.colors.primary : context.colors.border,
            ),
          ),
          child: Text(
            label,
            style: context.text.labelSm.copyWith(
              color: selected ? context.colors.primaryFg : context.colors.muted,
              fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
            ),
          ),
        ),
      ),
    );
  }
}

class _NoMatches extends StatelessWidget {
  const _NoMatches({required this.query});

  final String query;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: EdgeInsets.all(context.space.xl2),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.palette_outlined, size: 40, color: context.colors.muted),
            SizedBox(height: context.space.md),
            Text(
              query.isEmpty
                  ? 'Nothing in this group'
                  : 'No theme matches “$query”',
              textAlign: TextAlign.center,
              style: context.text.bodySm.copyWith(color: context.colors.muted),
            ),
          ],
        ),
      ),
    );
  }
}

/// One theme in the gallery: a miniature of the palette, its name, the line
/// describing it and its author.
///
/// Shared with the Settings strip's tap target so the two cannot describe the
/// same palette differently.
class ThemeRow extends StatelessWidget {
  const ThemeRow({
    required this.palette,
    required this.selected,
    required this.onTap,
    super.key,
  });

  final AppPalette palette;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      selected: selected,
      label: '${palette.name} theme',
      child: GestureDetector(
        key: Key('theme-swatch-${palette.id}'),
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Container(
          margin: EdgeInsets.fromLTRB(
            context.space.lg,
            0,
            context.space.lg,
            context.space.sm,
          ),
          padding: EdgeInsets.all(context.space.sm),
          decoration: BoxDecoration(
            color: selected
                ? context.colors.primary.withValues(alpha: 0.08)
                : context.colors.surface,
            borderRadius: BorderRadius.circular(context.radii.lg),
            border: Border.all(
              color: selected ? context.colors.primary : context.colors.border,
              width: selected ? 2 : 1,
            ),
          ),
          child: Row(
            children: [
              ThemeMiniature(palette: palette, width: 84, height: 56),
              SizedBox(width: context.space.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      palette.name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: context.text.label.copyWith(
                        color: context.colors.fg,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    if (palette.description.isNotEmpty) ...[
                      SizedBox(height: context.space.xxs),
                      Text(
                        palette.description,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: context.text.labelSm.copyWith(
                          color: context.colors.muted,
                        ),
                      ),
                    ],
                    if (palette.author.isNotEmpty) ...[
                      SizedBox(height: context.space.xxs),
                      Text(
                        palette.author,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: context.text.labelSm.copyWith(
                          color: context.colors.muted.withValues(alpha: 0.65),
                          fontSize: 10,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              SizedBox(width: context.space.sm),
              Icon(
                selected ? Icons.check_circle : Icons.circle_outlined,
                size: 20,
                color: selected ? context.colors.primary : context.colors.border,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// A palette painted in its own colours: page, a card on it with an "Aa"
/// sample, and the two accents as dots. Nothing here reads `context.colors` —
/// the point is to show a theme the app is NOT currently wearing.
class ThemeMiniature extends StatelessWidget {
  const ThemeMiniature({
    required this.palette,
    required this.width,
    required this.height,
    super.key,
  });

  final AppPalette palette;
  final double width;
  final double height;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: width,
      height: height,
      padding: EdgeInsets.all(context.space.xs),
      decoration: BoxDecoration(
        color: palette.bg,
        borderRadius: BorderRadius.circular(context.radii.md),
        border: Border.all(color: palette.border),
      ),
      child: Container(
        padding: EdgeInsets.symmetric(horizontal: context.space.xs),
        decoration: BoxDecoration(
          color: palette.surface,
          borderRadius: BorderRadius.circular(context.radii.sm),
          border: Border.all(color: palette.border),
        ),
        child: Row(
          children: [
            Flexible(
              child: Text(
                'Aa',
                maxLines: 1,
                overflow: TextOverflow.clip,
                style: TextStyle(
                  color: palette.fg,
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                  height: 1,
                ),
              ),
            ),
            const Spacer(),
            _dot(palette.primary),
            SizedBox(width: context.space.xxs),
            _dot(palette.accent),
          ],
        ),
      ),
    );
  }

  Widget _dot(Color color) => Container(
        width: 8,
        height: 8,
        decoration: BoxDecoration(color: color, shape: BoxShape.circle),
      );
}
