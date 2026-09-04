import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_metrics.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/app/theme/preset_controller.dart';
import 'package:manhwamaniacs/app/theme/theme_controller.dart';
import 'package:manhwamaniacs/core/config/env.dart';
import 'package:manhwamaniacs/features/auth/models/auth_state.dart';
import 'package:manhwamaniacs/features/auth/providers/auth_controller.dart';
import 'package:manhwamaniacs/features/profiles/providers/profile_scope.dart';
import 'package:manhwamaniacs/features/reader/providers/reader_filter_provider.dart';
import 'package:manhwamaniacs/features/settings/models/app_version.dart';
import 'package:manhwamaniacs/features/settings/models/reader_defaults.dart';
import 'package:manhwamaniacs/features/settings/providers/app_update_provider.dart';
import 'package:manhwamaniacs/features/settings/providers/settings_provider.dart';
import 'package:manhwamaniacs/features/settings/screens/theme_gallery_screen.dart';
import 'package:manhwamaniacs/features/settings/utils/settings_search_index.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/widgets/glass_card.dart';
import 'package:manhwamaniacs/shared/widgets/skeleton_box.dart';
import 'package:url_launcher/url_launcher.dart';

class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabController;
  final _apiUrlController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 4, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    _apiUrlController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          tooltip: 'Back',
          onPressed: () =>
              context.canPop() ? context.pop() : context.go(Routes.more),
        ),
        title: const Text('Settings'),
        actions: [
          IconButton(
            icon: const Icon(Icons.search),
            tooltip: 'Search settings',
            onPressed: () => showSearch(
              context: context,
              delegate: SettingsSearchDelegate(
                onSelectTab: _tabController.animateTo,
              ),
            ),
          ),
        ],
        bottom: TabBar(
          controller: _tabController,
          isScrollable: true,
          tabAlignment: TabAlignment.start,
          tabs: const [
            Tab(text: 'General'),
            Tab(text: 'Server'),
            Tab(text: 'About'),
            Tab(text: 'Debug'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: [
          const _GeneralSettingsPanel(),
          _ServerSettingsPanel(controller: _apiUrlController),
          const _AboutPanel(),
          const _DebugPanel(),
        ],
      ),
    );
  }
}

// ── General ──────────────────────────────────────────────────────────────

class _GeneralSettingsPanel extends StatelessWidget {
  const _GeneralSettingsPanel();

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: EdgeInsets.all(context.space.xl2),
      children: [
        const _SectionHeading('Account'),
        SizedBox(height: context.space.sm),
        const _AccountSection(),
        SizedBox(height: context.space.xl2),
        const _SectionHeading('Content'),
        SizedBox(height: context.space.sm),
        const _MatureContentToggle(),
        SizedBox(height: context.space.xl2),
        const _SectionHeading('History'),
        SizedBox(height: context.space.sm),
        const _HistorySection(),
        SizedBox(height: context.space.xl2),
        const _SectionHeading('Theme'),
        SizedBox(height: context.space.sm),
        const _ThemeSelector(),
        SizedBox(height: context.space.xl2),
        const _SectionHeading('Design'),
        SizedBox(height: context.space.sm),
        const _DesignSelector(),
        SizedBox(height: context.space.xl2),
        const _SectionHeading('Language'),
        SizedBox(height: context.space.sm),
        const _LanguageSelector(),
        SizedBox(height: context.space.xl2),
        const _SectionHeading('Feedback'),
        SizedBox(height: context.space.sm),
        const _HapticsToggle(),
        SizedBox(height: context.space.xl2),
        const _SectionHeading('Default reader preferences'),
        SizedBox(height: context.space.sm),
        const _ReaderDefaultsSection(),
      ],
    );
  }
}

/// Premium section eyebrow: a warm amber accent bar beside an uppercase Syne
/// label. Mirrors the design-system nav-label treatment (uppercase, wide
/// tracking) using the display typeface so every settings group reads as one
/// system.
class _SectionHeading extends StatelessWidget {
  const _SectionHeading(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(bottom: context.space.xxs),
      child: Row(
        children: [
          Container(
            width: 3,
            height: 15,
            decoration: BoxDecoration(
              color: context.colors.primary,
              borderRadius: BorderRadius.circular(context.radii.full),
            ),
          ),
          SizedBox(width: context.space.sm),
          Text(
            text.toUpperCase(),
            style: context.text.h1.copyWith(
              fontSize: 14,
              fontWeight: FontWeight.w600,
              letterSpacing: 2,
              color: context.colors.fg,
            ),
          ),
        ],
      ),
    );
  }
}

class _AccountSection extends ConsumerWidget {
  const _AccountSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(authControllerProvider);
    if (state is! AuthAuthenticated) return const SizedBox.shrink();
    final user = state.user;
    final initial =
        user.label.isNotEmpty ? user.label.substring(0, 1).toUpperCase() : '?';

    return GlassCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              CircleAvatar(
                backgroundColor: context.colors.primary,
                child: Text(
                  initial,
                  style: context.text.labelLg
                      .copyWith(color: context.colors.primaryFg),
                ),
              ),
              SizedBox(width: context.space.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(user.label, style: context.text.labelLg),
                    Text(
                      '@${user.username}',
                      style: context.text.bodySm
                          .copyWith(color: context.colors.muted),
                    ),
                  ],
                ),
              ),
              if (user.isAdmin) const _AdminBadge(),
            ],
          ),
          SizedBox(height: context.space.lg),
          OutlinedButton.icon(
            onPressed: () => _confirmSignOut(context, ref),
            icon: const Icon(Icons.logout, size: 18),
            label: const Text('Sign out'),
          ),
        ],
      ),
    );
  }

  Future<void> _confirmSignOut(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogCtx) => AlertDialog(
        title: const Text('Sign out?'),
        content: const Text('You will need to sign in again to use the app.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogCtx, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogCtx, true),
            child: const Text('Sign out'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    // The router (watching authControllerProvider) redirects to login once the
    // controller drops to unauthenticated, so no manual navigation is needed.
    await ref.read(authControllerProvider.notifier).logout();
  }
}

class _HistorySection extends StatelessWidget {
  const _HistorySection();

  @override
  Widget build(BuildContext context) {
    return GlassCard(
      onTap: () => context.push(Routes.readingHistory),
      glowColor: context.colors.primary,
      child: Row(
        children: [
          Container(
            padding: EdgeInsets.all(context.space.sm),
            decoration: BoxDecoration(
              color: context.colors.primary.withAlpha(30),
              borderRadius: BorderRadius.circular(context.radii.md),
              border: Border.all(color: context.colors.primary.withAlpha(64)),
            ),
            child: Icon(Icons.history_rounded, color: context.colors.primary),
          ),
          SizedBox(width: context.space.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Reading history', style: context.text.labelLg),
                SizedBox(height: context.space.xxs),
                Text(
                  'See what you read last',
                  style: context.text.bodySm.copyWith(color: context.colors.muted),
                ),
              ],
            ),
          ),
          Icon(Icons.chevron_right, color: context.colors.primary),
        ],
      ),
    );
  }
}

class _AdminBadge extends StatelessWidget {
  const _AdminBadge();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: context.space.sm,
        vertical: context.space.xxs,
      ),
      decoration: BoxDecoration(
        color: context.colors.primary.withAlpha(36),
        borderRadius: BorderRadius.circular(context.radii.full),
        border: Border.all(color: context.colors.primary.withAlpha(90)),
      ),
      child: Text(
        'Admin',
        style: context.text.labelSm.copyWith(color: context.colors.primary),
      ),
    );
  }
}

/// The Theme section: what the app is wearing, a strip to flick through
/// every palette, and a way into the full gallery.
///
/// This used to be the whole registry in one `Wrap`. Forty-five palettes do
/// not fit that shape — the section became taller than the rest of Settings
/// put together, and finding a named theme meant reading every tile. So the
/// section keeps the two things worth doing without leaving Settings (see
/// what is on, flick to the next one) and hands browsing to
/// [ThemeGalleryScreen], which has search and a dark/light filter.
class _ThemeSelector extends ConsumerWidget {
  const _ThemeSelector();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final active = ref.watch(themeControllerProvider);

    return GlassCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Semantics(
            button: true,
            label: 'Browse themes. Currently ${active.name}',
            child: GestureDetector(
              key: const Key('theme-open-gallery'),
              behavior: HitTestBehavior.opaque,
              onTap: () => Navigator.of(context).push<void>(
                MaterialPageRoute(
                  builder: (_) => const ThemeGalleryScreen(),
                ),
              ),
              child: Row(
                children: [
                  ThemeMiniature(palette: active, width: 84, height: 56),
                  SizedBox(width: context.space.md),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          active.name,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: context.text.label.copyWith(
                            color: context.colors.fg,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        SizedBox(height: context.space.xxs),
                        Text(
                          active.description.isEmpty
                              ? '${AppPalettes.all.length} themes'
                              : active.description,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: context.text.labelSm.copyWith(
                            color: context.colors.muted,
                          ),
                        ),
                      ],
                    ),
                  ),
                  SizedBox(width: context.space.xs),
                  Icon(
                    Icons.chevron_right,
                    size: 20,
                    color: context.colors.muted,
                  ),
                ],
              ),
            ),
          ),
          SizedBox(height: context.space.md),
          _ThemeStrip(activeId: active.id),
        ],
      ),
    );
  }
}

/// Every palette as a thumbnail on one horizontal rail.
///
/// Deliberately nameless: at this size a caption would truncate to
/// "Gruvbox Mat…" and the row above already says what is selected. This is for
/// flicking until something looks right; the gallery is for looking one up.
class _ThemeStrip extends ConsumerWidget {
  const _ThemeStrip({required this.activeId});

  final String activeId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return SizedBox(
      height: 52,
      child: ListView.separated(
        key: const Key('theme-strip'),
        scrollDirection: Axis.horizontal,
        clipBehavior: Clip.none,
        itemCount: AppPalettes.all.length,
        separatorBuilder: (_, __) => SizedBox(width: context.space.sm),
        itemBuilder: (context, index) {
          final palette = AppPalettes.all[index];
          final selected = palette.id == activeId;
          return Semantics(
            button: true,
            selected: selected,
            label: '${palette.name} theme',
            child: GestureDetector(
              key: Key('theme-strip-${palette.id}'),
              onTap: () {
                ref.read(hapticsProvider).selection();
                ref.read(themeControllerProvider.notifier).setTheme(palette.id);
              },
              child: Stack(
                children: [
                  DecoratedBox(
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(context.radii.md),
                      border: Border.all(
                        color: selected
                            ? context.colors.primary
                            : Colors.transparent,
                        width: 2,
                      ),
                    ),
                    child: Padding(
                      padding: const EdgeInsets.all(2),
                      child: ThemeMiniature(
                        palette: palette,
                        width: 64,
                        height: 44,
                      ),
                    ),
                  ),
                  if (selected)
                    Positioned(
                      top: 4,
                      right: 4,
                      child: Container(
                        padding: const EdgeInsets.all(1),
                        decoration: BoxDecoration(
                          color: palette.primary,
                          shape: BoxShape.circle,
                        ),
                        child: Icon(
                          Icons.check,
                          size: 10,
                          color: palette.primaryFg,
                        ),
                      ),
                    ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}

/// The design-preset picker: one row per preset, each with a live miniature
/// drawn in the *current* palette so the two axes are visibly independent —
/// change the theme and every preview recolours without changing shape.
///
/// Applies on tap, like the theme gallery, and persists per profile (see
/// `preset_controller.dart`). Nothing here needs a restart: the preset is a
/// ThemeExtension, so selecting one rebuilds the tree the same way a palette
/// switch does, and the reader keeps its place.
class _DesignSelector extends ConsumerWidget {
  const _DesignSelector();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final active = ref.watch(presetControllerProvider);

    return GlassCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final preset in AppPresets.all) ...[
            if (preset != AppPresets.all.first)
              SizedBox(height: context.space.sm),
            _PresetRow(
              preset: preset,
              selected: preset.id == active.id,
              onTap: () {
                ref.read(hapticsProvider).selection();
                ref.read(presetControllerProvider.notifier).setPreset(preset.id);
              },
            ),
          ],
        ],
      ),
    );
  }
}

/// One tappable preset: its shape in miniature, its name, and the position it
/// takes in one line.
class _PresetRow extends StatelessWidget {
  const _PresetRow({
    required this.preset,
    required this.selected,
    required this.onTap,
  });

  final AppMetrics preset;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      selected: selected,
      label: '${preset.name} design',
      child: InkWell(
        key: Key('preset-row-${preset.id}'),
        onTap: onTap,
        borderRadius: BorderRadius.circular(context.radii.md),
        child: Padding(
          padding: EdgeInsets.all(context.space.sm),
          child: Row(
            children: [
              _PresetPreview(preset: preset),
              SizedBox(width: context.space.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      preset.name,
                      style: context.text.labelLg.copyWith(
                        color: context.colors.fg,
                        fontWeight:
                            selected ? FontWeight.w700 : FontWeight.w500,
                      ),
                    ),
                    SizedBox(height: context.space.xxs),
                    Text(
                      preset.description,
                      style: context.text.caption
                          .copyWith(color: context.colors.muted),
                    ),
                  ],
                ),
              ),
              SizedBox(width: context.space.sm),
              Icon(
                selected ? Icons.radio_button_checked : Icons.radio_button_off,
                size: 20,
                color:
                    selected ? context.colors.primary : context.colors.border,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// A miniature of what the preset does: a card at that preset's radius, border
/// weight and surface treatment, holding a heading in its face and two rows at
/// its spacing rhythm.
///
/// Drawn from `preset.*` rather than `context.*` — the point is to show a
/// preset that is *not* the active one — but coloured entirely from
/// `context.colors`, which is exactly the orthogonality the two axes promise.
class _PresetPreview extends StatelessWidget {
  const _PresetPreview({required this.preset});

  final AppMetrics preset;

  static const double _width = 64;
  static const double _height = 48;

  @override
  Widget build(BuildContext context) {
    final surfaces = preset.surfaces;
    final line = context.colors.muted.withValues(alpha: 0.5);

    return Container(
      width: _width,
      height: _height,
      padding: EdgeInsets.all(preset.space.sm),
      decoration: BoxDecoration(
        color: context.colors.surface2
            .withValues(alpha: surfaces.isGlass ? 0.6 : 1),
        borderRadius: BorderRadius.circular(preset.radii.lg),
        border: Border.all(
          color: surfaces.cardBorderIsStrong
              ? context.colors.border
              : context.colors.glassEdge,
          width: preset.strokes.border,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(
            'Aa',
            style: preset.text.h4.copyWith(
              color: context.colors.fg,
              fontSize: 13,
              height: 1,
            ),
          ),
          SizedBox(height: preset.space.xs),
          for (var i = 0; i < 2; i++) ...[
            if (i > 0) SizedBox(height: preset.space.xxs),
            Container(
              height: 2,
              width: i == 0 ? _width * 0.5 : _width * 0.34,
              decoration: BoxDecoration(
                color: line,
                borderRadius: BorderRadius.circular(preset.radii.xs),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _LanguageSelector extends ConsumerWidget {
  const _LanguageSelector();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final language = ref.watch(languageProvider);

    return GlassCard(
      child: DropdownButtonFormField<AppLanguage>(
        initialValue: language,
        decoration: const InputDecoration(labelText: 'App language'),
        items: AppLanguage.values
            .map(
              (lang) => DropdownMenuItem(value: lang, child: Text(lang.label)),
            )
            .toList(),
        onChanged: (value) {
          if (value != null) {
            ref.read(languageProvider.notifier).setLanguage(value);
          }
        },
      ),
    );
  }
}

class _HapticsToggle extends ConsumerWidget {
  const _HapticsToggle();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final enabled = ref.watch(hapticFeedbackProvider);

    return GlassCard(
      // SwitchListTile paints its splash on the nearest Material ancestor;
      // GlassCard only supplies one when onTap is set.
      child: Material(
        color: Colors.transparent,
        child: SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Haptic feedback'),
          subtitle: const Text(
            'Subtle vibrations on page turns, chapter changes and actions',
          ),
          value: enabled,
          onChanged: (value) =>
              ref.read(hapticFeedbackProvider.notifier).setEnabled(value),
        ),
      ),
    );
  }
}

/// Per-profile "Mature 18+" toggle. Reads the active profile's
/// `mature_content_enabled` from `GET /settings` and writes it back via
/// `PUT /settings`; because the underlying provider is invalidated on a profile
/// switch, switching profiles shows that profile's own value. A failed write is
/// rolled back by the controller and surfaced as a snackbar (routing back to the
/// picker if the backend rejects the profile scope).
class _MatureContentToggle extends ConsumerWidget {
  const _MatureContentToggle();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(matureContentProvider);

    // Initial load failed and there's no cached value to fall back on: show a
    // compact, self-contained retry card instead of a dead switch, so this
    // network-backed section degrades on its own without red-outing the tab.
    if (async.hasError && !async.hasValue) {
      return _SectionErrorCard(
        label: 'the mature content setting',
        onRetry: () => ref.invalidate(matureContentProvider),
      );
    }

    return GlassCard(
      // SwitchListTile paints its splash on the nearest Material ancestor;
      // GlassCard only supplies one when onTap is set.
      child: Material(
        color: Colors.transparent,
        child: SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Show mature content (18+)'),
          subtitle: const Text(
            'Include adult-only series in browsing, search and sources '
            'for this profile. Enabling requires confirming you are 18 or '
            'older.',
          ),
          value: async.valueOrNull ?? false,
          onChanged: async.isLoading
              ? null
              : (value) => _onToggle(context, ref, value),
        ),
      ),
    );
  }

  Future<void> _onToggle(
    BuildContext context,
    WidgetRef ref,
    bool value,
  ) async {
    // Turning the gate ON requires an explicit age confirmation first (mirrors
    // the web MatureContentPanel); turning it OFF applies immediately.
    if (value) {
      final confirmed = await _confirmEnable(context);
      if (confirmed != true) return;
    }
    if (!context.mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    final error =
        await ref.read(matureContentProvider.notifier).setEnabled(value);
    if (error == null) return;
    if (recoverFromProfileScopeError(ref, error)) return;
    messenger.showSnackBar(SnackBar(content: Text(error.userMessage)));
  }

  Future<bool?> _confirmEnable(BuildContext context) {
    return showDialog<bool>(
      context: context,
      builder: (dialogCtx) => AlertDialog(
        title: const Text('Enable mature content?'),
        content: const Text(
          'This shows adult (18+) sources, search results and recommendations '
          'throughout ManhwaManiacs. Only continue if you are of legal age to '
          'view mature content where you live. You can turn this off again at '
          'any time.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogCtx, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogCtx, true),
            child: const Text('I am 18 or older — Enable'),
          ),
        ],
      ),
    );
  }
}

/// Compact, self-contained error boundary for a single settings section that
/// depends on a network provider. One section failing renders just this card
/// (with an inline retry that re-fetches only that provider) instead of
/// red-outing the whole tab.
class _SectionErrorCard extends StatelessWidget {
  const _SectionErrorCard({required this.label, required this.onRetry});

  final String label;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return GlassCard(
      child: Row(
        children: [
          Icon(
            Icons.error_outline_rounded,
            color: context.colors.muted,
            size: 18,
          ),
          SizedBox(width: context.space.sm),
          Expanded(
            child: Text(
              "Couldn't load $label.",
              style: context.text.bodySm.copyWith(color: context.colors.muted),
            ),
          ),
          SizedBox(width: context.space.sm),
          TextButton(onPressed: onRetry, child: const Text('Retry')),
        ],
      ),
    );
  }
}

class _ReaderDefaultsSection extends ConsumerWidget {
  const _ReaderDefaultsSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final defaults = ref.watch(readerDefaultsProvider);
    final notifier = ref.read(readerDefaultsProvider.notifier);
    // Refresh rate is `flutter_displaymode` and volume-key paging is the
    // `NativeBridge` method channel; both are Android-only and already no-op
    // elsewhere (reader_display_mode.dart, native_bridge.dart). Showing live
    // controls that save a preference and then do nothing is worse than not
    // showing them, so hide rather than disable.
    final hasDisplayModes = Theme.of(context).platform == TargetPlatform.android;

    return GlassCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: EdgeInsets.only(bottom: context.space.xs),
            child: Text('Reading direction', style: context.text.labelLg),
          ),
          SegmentedButton<ReadingDirection>(
            segments: ReadingDirection.values
                .map((d) => ButtonSegment(value: d, label: Text(d.label)))
                .toList(),
            selected: {defaults.direction},
            onSelectionChanged: (selection) =>
                notifier.setDirection(selection.first),
          ),
          SizedBox(height: context.space.lg),
          Padding(
            padding: EdgeInsets.only(bottom: context.space.xs),
            child: Text('Fit mode', style: context.text.labelLg),
          ),
          SegmentedButton<ReaderFitMode>(
            segments: ReaderFitMode.values
                .map((f) => ButtonSegment(value: f, label: Text(f.label)))
                .toList(),
            selected: {defaults.fitMode},
            onSelectionChanged: (selection) =>
                notifier.setFitMode(selection.first),
          ),
          if (hasDisplayModes) ...[
            SizedBox(height: context.space.lg),
            Padding(
              padding: EdgeInsets.only(bottom: context.space.xxs),
              child: Text('Refresh rate', style: context.text.labelLg),
            ),
            Padding(
              padding: EdgeInsets.only(bottom: context.space.sm),
              child: Text(
                'Auto uses the highest rate your screen supports.',
                style: context.text.bodySm.copyWith(color: context.colors.muted),
              ),
            ),
            Wrap(
              spacing: context.space.sm,
              runSpacing: context.space.xs,
              children: ReaderRefreshRate.values.map((rate) {
                return ChoiceChip(
                  label: Text(rate.label),
                  selected: defaults.refreshRate == rate,
                  onSelected: (_) => notifier.setRefreshRate(rate),
                );
              }).toList(),
            ),
          ],
          SizedBox(height: context.space.sm),
          // SwitchListTile paints on the nearest Material ancestor; GlassCard
          // doesn't provide one unless onTap is set.
          Material(
            color: Colors.transparent,
            child: Column(
              children: [
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Keep screen awake'),
                  value: defaults.keepScreenAwake,
                  onChanged: notifier.setKeepScreenAwake,
                ),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Auto next chapter'),
                  value: defaults.autoNextChapter,
                  onChanged: notifier.setAutoNextChapter,
                ),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Lock reader controls'),
                  subtitle: const Text(
                    'Tap center 5× to unlock during reading',
                  ),
                  value: defaults.lockControls,
                  onChanged: notifier.setLockControls,
                ),
                if (hasDisplayModes)
                  SwitchListTile(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('Volume key navigation'),
                    subtitle: const Text(
                      'Turn pages with the volume buttons',
                    ),
                    value: defaults.volumeKeyNavigation,
                    onChanged: notifier.setVolumeKeyNavigation,
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ── Server ───────────────────────────────────────────────────────────────

class _ServerSettingsPanel extends ConsumerWidget {
  const _ServerSettingsPanel({required this.controller});

  final TextEditingController controller;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final apiUrlAsync = ref.watch(settingsApiUrlProvider);

    return apiUrlAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (error, _) => Center(child: Text(error.toString())),
      data: (url) {
        if (controller.text.isEmpty) controller.text = url;
        return ListView(
          padding: EdgeInsets.all(context.space.xl2),
          children: [
            const _SectionHeading('Server connection'),
            SizedBox(height: context.space.sm),
            Text(
              'Configure the ManhwaManiacs backend URL for this device.',
              style: context.text.body.copyWith(color: context.colors.muted),
            ),
            SizedBox(height: context.space.xl2),
            TextField(
              controller: controller,
              decoration: const InputDecoration(
                labelText: 'API base URL',
                hintText: Env.defaultApiUrl,
              ),
              keyboardType: TextInputType.url,
            ),
            SizedBox(height: context.space.lg),
            FilledButton(
              onPressed: () async {
                final error = await ref
                    .read(settingsActionsProvider)
                    .saveApiUrl(controller.text);
                if (!context.mounted) return;
                if (error == null) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(
                      content: Text('Server URL saved and applied.'),
                    ),
                  );
                } else {
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(content: Text(error.userMessage)),
                  );
                }
              },
              child: const Text('Save URL'),
            ),
            SizedBox(height: context.space.sm),
            OutlinedButton(
              onPressed: () async {
                await ref.read(settingsActionsProvider).resetApiUrl();
                // Guard the async gap: if the screen was popped during the
                // reset, `controller` is already disposed and writing to it
                // throws (mirrors the Save URL handler above).
                if (!context.mounted) return;
                controller.text = Env.defaultApiUrl;
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Reset to default URL.')),
                );
              },
              child: const Text('Reset to default'),
            ),
          ],
        );
      },
    );
  }
}

// ── About ────────────────────────────────────────────────────────────────

class _AboutPanel extends ConsumerWidget {
  const _AboutPanel();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final infoAsync = ref.watch(packageInfoProvider);
    final channel = AppUpdateChannel.forPlatform(Theme.of(context).platform);

    return ListView(
      padding: EdgeInsets.all(context.space.xl2),
      children: [
        const _SectionHeading('About'),
        SizedBox(height: context.space.xl2),
        infoAsync.when(
          loading: () => const SkeletonBox(width: double.infinity, height: 100),
          error: (_, __) => Text(
            'Unable to read app info',
            style: context.text.body.copyWith(color: context.colors.muted),
          ),
          data: (info) => GlassCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('ManhwaManiacs', style: context.text.h3),
                SizedBox(height: context.space.xs),
                Text(
                  'Local-first manga & manhwa reader',
                  style: context.text.bodySm.copyWith(color: context.colors.muted),
                ),
                SizedBox(height: context.space.lg),
                _InfoRow(label: 'Version', value: info.version),
                SizedBox(height: context.space.sm),
                _InfoRow(label: 'Build', value: info.buildNumber),
              ],
            ),
          ),
        ),
        SizedBox(height: context.space.lg),
        // Update check
        const _SectionHeading('Updates'),
        SizedBox(height: context.space.sm),
        // The two channels are not comparable, so neither is their UI: the
        // APK card runs a build-number check the SideStore channel has no
        // equivalent for. See AppVersionInfo.hasUpdate.
        if (channel == AppUpdateChannel.sideStore)
          const _SideStoreUpdateCard()
        else
          const _ApkUpdateCard(),
        SizedBox(height: context.space.lg),
        OutlinedButton(
          onPressed: () {
            final info = infoAsync.valueOrNull;
            showLicensePage(
              context: context,
              applicationName: info?.appName ?? 'ManhwaManiacs',
              applicationVersion: info?.version,
            );
          },
          child: const Text('Open source licenses'),
        ),
      ],
    );
  }
}

/// The Updates section on the Android APK channel: check `/app/version`
/// and offer the release APK when the backend is ahead of the install.
class _ApkUpdateCard extends ConsumerWidget {
  const _ApkUpdateCard();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ref.watch(appUpdateProvider).when(
      loading: () => const SkeletonBox(width: double.infinity, height: 64),
      error: (_, __) => GlassCard(
        child: Row(
          children: [
            Icon(
              Icons.cloud_off_outlined,
              color: context.colors.muted,
              size: 18,
            ),
            SizedBox(width: context.space.sm),
            Text(
              'Could not check for updates',
              style: context.text.body.copyWith(color: context.colors.muted),
            ),
          ],
        ),
      ),
      data: (info) {
        if (info == null) {
          return GlassCard(
            child: Row(
              children: [
                Icon(
                  Icons.cloud_off_outlined,
                  color: context.colors.muted,
                  size: 18,
                ),
                SizedBox(width: context.space.sm),
                Text(
                  'Server unreachable',
                  style:
                      context.text.body.copyWith(color: context.colors.muted),
                ),
              ],
            ),
          );
        }
        if (!info.hasUpdate) {
          return GlassCard(
            child: Row(
              children: [
                Icon(
                  Icons.check_circle_outline,
                  color: context.colors.success,
                  size: 18,
                ),
                SizedBox(width: context.space.sm),
                Text(
                  'Up to date — v${info.localVersion}',
                  style: context.text.body,
                ),
              ],
            ),
          );
        }
        return GlassCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(
                    Icons.system_update_outlined,
                    color: context.colors.primary,
                    size: 18,
                  ),
                  SizedBox(width: context.space.sm),
                  Text(
                    'Update available',
                    style: context.text.labelLg.copyWith(
                      color: context.colors.primary,
                    ),
                  ),
                ],
              ),
              SizedBox(height: context.space.xs),
              Text(
                'v${info.localVersion} → v${info.remoteVersion}',
                style:
                    context.text.bodySm.copyWith(color: context.colors.muted),
              ),
              SizedBox(height: context.space.md),
              OutlinedButton.icon(
                onPressed: () async {
                  final uri = Uri.tryParse(info.downloadUrl);
                  if (uri == null) return;
                  final launched = await launchUrl(
                    uri,
                    mode: LaunchMode.externalApplication,
                  );
                  if (!launched && context.mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text('Could not open: ${info.downloadUrl}'),
                      ),
                    );
                  }
                },
                icon: const Icon(Icons.download_outlined, size: 16),
                label: const Text('Download Update'),
              ),
            ],
          ),
        );
      },
    );
  }
}

/// The Updates section on a sideloaded iOS build.
///
/// There is deliberately nothing to tap here. The app is installed through
/// SideStore on a free Apple ID: SideStore subscribes to the source manifest
/// below, compares it against what is installed, and does the install and the
/// 7-day re-sign itself. Anything this screen offered instead would be a lie —
/// `/app/download` is an Android `.apk`, and a raw `.ipa` cannot be installed
/// by a process that has no way to sign it.
class _SideStoreUpdateCard extends ConsumerWidget {
  const _SideStoreUpdateCard();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final sourceUrl = AppVersionInfo.sourceUrlFor(
      AppUpdateChannel.sideStore,
      ref.watch(apiBaseUrlProvider),
    );

    return GlassCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                Icons.install_mobile_outlined,
                color: context.colors.primary,
                size: 18,
              ),
              SizedBox(width: context.space.sm),
              Text(
                'Managed by SideStore',
                style: context.text.labelLg.copyWith(
                  color: context.colors.primary,
                ),
              ),
            ],
          ),
          SizedBox(height: context.space.xs),
          Text(
            'This build is sideloaded. SideStore watches the source below and '
            'offers new builds itself — there is nothing to download here.',
            style: context.text.bodySm.copyWith(color: context.colors.muted),
          ),
          SizedBox(height: context.space.md),
          SelectableText(
            sourceUrl,
            style: context.text.bodySm.copyWith(color: context.colors.fg),
          ),
          SizedBox(height: context.space.sm),
          OutlinedButton.icon(
            onPressed: () async {
              await Clipboard.setData(ClipboardData(text: sourceUrl));
              if (!context.mounted) return;
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Source URL copied')),
              );
            },
            icon: const Icon(Icons.copy_outlined, size: 16),
            label: const Text('Copy source URL'),
          ),
          SizedBox(height: context.space.md),
          Text(
            'A free Apple ID signature lasts 7 days. If the app stops '
            'launching, open SideStore and refresh it — re-signing with the '
            'same Apple ID keeps you signed in here.',
            style: context.text.caption.copyWith(color: context.colors.muted),
          ),
        ],
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: context.text.body.copyWith(color: context.colors.muted)),
        SizedBox(width: context.space.md),
        Flexible(
          child: Text(
            value,
            style: context.text.labelLg,
            textAlign: TextAlign.right,
          ),
        ),
      ],
    );
  }
}

// ── Debug ────────────────────────────────────────────────────────────────

class _DebugPanel extends ConsumerWidget {
  const _DebugPanel();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ListView(
      padding: EdgeInsets.all(context.space.xl2),
      children: [
        const _SectionHeading('Diagnostics'),
        SizedBox(height: context.space.sm),
        GlassCard(
          onTap: () => context.push(Routes.diagnostics),
          child: Row(
            children: [
              Icon(Icons.speed_rounded, color: context.colors.primary),
              SizedBox(width: context.space.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Performance & display', style: context.text.labelLg),
                    SizedBox(height: context.space.xxs),
                    Text(
                      // Refresh rate is only a readable/switchable thing on
                      // Android (`flutter_displaymode`); do not advertise it
                      // where the diagnostics screen reports "unsupported".
                      Theme.of(context).platform == TargetPlatform.android
                          ? 'Refresh rate, FPS, frame timing, device info, cache'
                          : 'FPS, frame timing, device info, cache',
                      style: context.text.bodySm
                          .copyWith(color: context.colors.muted),
                    ),
                  ],
                ),
              ),
              Icon(Icons.chevron_right, color: context.colors.muted, size: 18),
            ],
          ),
        ),
        SizedBox(height: context.space.xl2),
        const _SectionHeading('Reset'),
        SizedBox(height: context.space.sm),
        GlassCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'Restore reader defaults',
                style: context.text.labelLg,
              ),
              SizedBox(height: context.space.xs),
              Text(
                'Resets direction, fit, brightness, warmth, background, color '
                'mode and refresh rate. Server URL and library are untouched.',
                style: context.text.bodySm.copyWith(color: context.colors.muted),
              ),
              SizedBox(height: context.space.md),
              OutlinedButton.icon(
                onPressed: () => _confirmResetReader(context, ref),
                icon: const Icon(Icons.restart_alt, size: 18),
                label: const Text('Reset reader settings'),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Future<void> _confirmResetReader(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogCtx) => AlertDialog(
        title: const Text('Reset reader settings?'),
        content: const Text(
          'This restores all reader preferences to their defaults.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogCtx, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogCtx, true),
            child: const Text('Reset'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    await ref.read(preferencesProvider).resetReaderPreferences();
    ref.invalidate(readerDefaultsProvider);
    ref.invalidate(readerFilterProvider);
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Reader settings reset to defaults.')),
      );
    }
  }
}
