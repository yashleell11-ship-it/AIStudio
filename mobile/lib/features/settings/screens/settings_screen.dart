import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/core/config/env.dart';
import 'package:manhwamaniacs/features/auth/models/auth_state.dart';
import 'package:manhwamaniacs/features/auth/providers/auth_controller.dart';
import 'package:manhwamaniacs/features/downloads/models/download_settings.dart';
import 'package:manhwamaniacs/features/profiles/providers/profile_scope.dart';
import 'package:manhwamaniacs/features/reader/providers/reader_filter_provider.dart';
import 'package:manhwamaniacs/features/settings/models/app_version.dart';
import 'package:manhwamaniacs/features/settings/models/reader_defaults.dart';
import 'package:manhwamaniacs/features/settings/providers/app_update_provider.dart';
import 'package:manhwamaniacs/features/settings/providers/settings_provider.dart';
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
      padding: const EdgeInsets.all(AppSpacing.xl2),
      children: const [
        _SectionHeading('Account'),
        SizedBox(height: AppSpacing.sm),
        _AccountSection(),
        SizedBox(height: AppSpacing.xl2),
        _SectionHeading('Content'),
        SizedBox(height: AppSpacing.sm),
        _MatureContentToggle(),
        SizedBox(height: AppSpacing.xl2),
        _SectionHeading('History'),
        SizedBox(height: AppSpacing.sm),
        _HistorySection(),
        SizedBox(height: AppSpacing.xl2),
        _SectionHeading('Theme'),
        SizedBox(height: AppSpacing.sm),
        _ThemeSelector(),
        SizedBox(height: AppSpacing.xl2),
        _SectionHeading('Language'),
        SizedBox(height: AppSpacing.sm),
        _LanguageSelector(),
        SizedBox(height: AppSpacing.xl2),
        _SectionHeading('Feedback'),
        SizedBox(height: AppSpacing.sm),
        _HapticsToggle(),
        SizedBox(height: AppSpacing.xl2),
        _SectionHeading('Default reader preferences'),
        SizedBox(height: AppSpacing.sm),
        _ReaderDefaultsSection(),
        SizedBox(height: AppSpacing.xl2),
        _SectionHeading('Download preferences'),
        SizedBox(height: AppSpacing.sm),
        _DownloadPreferencesSection(),
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
      padding: const EdgeInsets.only(bottom: AppSpacing.xxs),
      child: Row(
        children: [
          Container(
            width: 3,
            height: 15,
            decoration: BoxDecoration(
              color: AppColors.primary,
              borderRadius: BorderRadius.circular(AppRadius.full),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Text(
            text.toUpperCase(),
            style: AppTypography.h1.copyWith(
              fontSize: 14,
              fontWeight: FontWeight.w600,
              letterSpacing: 2,
              color: AppColors.fg,
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
                backgroundColor: AppColors.primary,
                child: Text(
                  initial,
                  style: AppTypography.labelLg
                      .copyWith(color: AppColors.primaryFg),
                ),
              ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(user.label, style: AppTypography.labelLg),
                    Text(
                      '@${user.username}',
                      style: AppTypography.bodySm
                          .copyWith(color: AppColors.muted),
                    ),
                  ],
                ),
              ),
              if (user.isAdmin) const _AdminBadge(),
            ],
          ),
          const SizedBox(height: AppSpacing.lg),
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
      glowColor: AppColors.primary,
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(AppSpacing.sm),
            decoration: BoxDecoration(
              color: AppColors.primary.withAlpha(30),
              borderRadius: BorderRadius.circular(AppRadius.md),
              border: Border.all(color: AppColors.primary.withAlpha(64)),
            ),
            child: const Icon(Icons.history_rounded, color: AppColors.primary),
          ),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Reading history', style: AppTypography.labelLg),
                const SizedBox(height: AppSpacing.xxs),
                Text(
                  'See what you read last',
                  style: AppTypography.bodySm.copyWith(color: AppColors.muted),
                ),
              ],
            ),
          ),
          const Icon(Icons.chevron_right, color: AppColors.primary),
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
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.sm,
        vertical: AppSpacing.xxs,
      ),
      decoration: BoxDecoration(
        color: AppColors.primary.withAlpha(36),
        borderRadius: BorderRadius.circular(AppRadius.full),
        border: Border.all(color: AppColors.primary.withAlpha(90)),
      ),
      child: Text(
        'Admin',
        style: AppTypography.labelSm.copyWith(color: AppColors.primary),
      ),
    );
  }
}

class _ThemeSelector extends ConsumerWidget {
  const _ThemeSelector();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final themeMode = ref.watch(themeModeProvider);

    return GlassCard(
      // RadioListTile paints its selection/splash on the nearest Material
      // ancestor; GlassCard only provides one when onTap is set, so this
      // needs its own.
      child: Material(
        color: Colors.transparent,
        child: RadioGroup<ThemeMode>(
          groupValue: themeMode,
          onChanged: (value) {
            if (value != null) {
              ref.read(themeModeProvider.notifier).setThemeMode(value);
            }
          },
          child: Column(
            children: ThemeMode.values.map((mode) {
              return RadioListTile<ThemeMode>(
                title: Text(_themeModeLabel(mode)),
                value: mode,
              );
            }).toList(),
          ),
        ),
      ),
    );
  }

  String _themeModeLabel(ThemeMode mode) => switch (mode) {
        ThemeMode.system => 'System',
        ThemeMode.light => 'Light',
        ThemeMode.dark => 'Dark',
      };
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
          const Icon(
            Icons.error_outline_rounded,
            color: AppColors.muted,
            size: 18,
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              "Couldn't load $label.",
              style: AppTypography.bodySm.copyWith(color: AppColors.muted),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
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
            padding: const EdgeInsets.only(bottom: AppSpacing.xs),
            child: Text('Reading direction', style: AppTypography.labelLg),
          ),
          SegmentedButton<ReadingDirection>(
            segments: ReadingDirection.values
                .map((d) => ButtonSegment(value: d, label: Text(d.label)))
                .toList(),
            selected: {defaults.direction},
            onSelectionChanged: (selection) =>
                notifier.setDirection(selection.first),
          ),
          const SizedBox(height: AppSpacing.lg),
          Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.xs),
            child: Text('Fit mode', style: AppTypography.labelLg),
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
            const SizedBox(height: AppSpacing.lg),
            Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.xxs),
              child: Text('Refresh rate', style: AppTypography.labelLg),
            ),
            Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.sm),
              child: Text(
                'Auto uses the highest rate your screen supports.',
                style: AppTypography.bodySm.copyWith(color: AppColors.muted),
              ),
            ),
            Wrap(
              spacing: AppSpacing.sm,
              runSpacing: AppSpacing.xs,
              children: ReaderRefreshRate.values.map((rate) {
                return ChoiceChip(
                  label: Text(rate.label),
                  selected: defaults.refreshRate == rate,
                  onSelected: (_) => notifier.setRefreshRate(rate),
                );
              }).toList(),
            ),
          ],
          const SizedBox(height: AppSpacing.sm),
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

class _DownloadPreferencesSection extends ConsumerStatefulWidget {
  const _DownloadPreferencesSection();

  @override
  ConsumerState<_DownloadPreferencesSection> createState() =>
      _DownloadPreferencesSectionState();
}

class _DownloadPreferencesSectionState
    extends ConsumerState<_DownloadPreferencesSection> {
  DownloadSettings? _draft;
  var _saving = false;

  @override
  Widget build(BuildContext context) {
    final wifiOnly = ref.watch(wifiOnlyDownloadsProvider);
    final settingsAsync = ref.watch(downloadSettingsProvider);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        GlassCard(
          // SwitchListTile paints on the nearest Material ancestor; GlassCard
          // doesn't provide one unless onTap is set.
          child: Material(
            color: Colors.transparent,
            child: SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Wi-Fi only'),
              subtitle:
                  const Text('Only download chapters while connected to Wi-Fi'),
              value: wifiOnly,
              onChanged: (value) => ref
                  .read(wifiOnlyDownloadsProvider.notifier)
                  .setEnabled(value),
            ),
          ),
        ),
        const SizedBox(height: AppSpacing.lg),
        settingsAsync.when(
          loading: () => const SkeletonBox(width: double.infinity, height: 180),
          // Isolated retry, not a full-tab error: a failed GET /downloads/settings
          // (which surfaces as UnknownError → "Something went wrong…") stays
          // contained to this section while the Wi-Fi toggle above still renders.
          error: (error, _) => _SectionErrorCard(
            label: 'download preferences',
            onRetry: () {
              _draft = null;
              ref.invalidate(downloadSettingsProvider);
            },
          ),
          data: (settings) {
            _draft ??= settings;
            final draft = _draft!;

            return GlassCard(
              child: Column(
                children: [
                  _SliderField(
                    label: 'Concurrent chapters',
                    value: draft.concurrentChapters.toDouble(),
                    min: 1,
                    max: 8,
                    divisions: 7,
                    onChanged: (value) => setState(
                      () => _draft = DownloadSettings(
                        concurrentChapters: value.round(),
                        pageConcurrency: draft.pageConcurrency,
                        retryCount: draft.retryCount,
                        retryDelaySeconds: draft.retryDelaySeconds,
                        timeoutSeconds: draft.timeoutSeconds,
                        activeDownloadCount: draft.activeDownloadCount,
                      ),
                    ),
                  ),
                  _SliderField(
                    label: 'Page concurrency',
                    value: draft.pageConcurrency.toDouble(),
                    min: 1,
                    max: 16,
                    divisions: 15,
                    onChanged: (value) => setState(
                      () => _draft = DownloadSettings(
                        concurrentChapters: draft.concurrentChapters,
                        pageConcurrency: value.round(),
                        retryCount: draft.retryCount,
                        retryDelaySeconds: draft.retryDelaySeconds,
                        timeoutSeconds: draft.timeoutSeconds,
                        activeDownloadCount: draft.activeDownloadCount,
                      ),
                    ),
                  ),
                  _SliderField(
                    label: 'Retry count',
                    value: draft.retryCount.toDouble(),
                    min: 0,
                    max: 10,
                    divisions: 10,
                    onChanged: (value) => setState(
                      () => _draft = DownloadSettings(
                        concurrentChapters: draft.concurrentChapters,
                        pageConcurrency: draft.pageConcurrency,
                        retryCount: value.round(),
                        retryDelaySeconds: draft.retryDelaySeconds,
                        timeoutSeconds: draft.timeoutSeconds,
                        activeDownloadCount: draft.activeDownloadCount,
                      ),
                    ),
                  ),
                  const SizedBox(height: AppSpacing.md),
                  FilledButton(
                    onPressed: _saving
                        ? null
                        : () async {
                            setState(() => _saving = true);
                            final error = await ref
                                .read(settingsActionsProvider)
                                .saveDownloadSettings(draft);
                            if (!context.mounted) return;
                            setState(() => _saving = false);
                            if (error == null) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(
                                  content: Text('Download settings saved.'),
                                ),
                              );
                            } else {
                              ScaffoldMessenger.of(context).showSnackBar(
                                SnackBar(content: Text(error.userMessage)),
                              );
                            }
                          },
                    child: Text(_saving ? 'Saving…' : 'Save download settings'),
                  ),
                ],
              ),
            );
          },
        ),
      ],
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
          padding: const EdgeInsets.all(AppSpacing.xl2),
          children: [
            const _SectionHeading('Server connection'),
            const SizedBox(height: AppSpacing.sm),
            Text(
              'Configure the ManhwaManiacs backend URL for this device.',
              style: AppTypography.body.copyWith(color: AppColors.muted),
            ),
            const SizedBox(height: AppSpacing.xl2),
            TextField(
              controller: controller,
              decoration: const InputDecoration(
                labelText: 'API base URL',
                hintText: Env.defaultApiUrl,
              ),
              keyboardType: TextInputType.url,
            ),
            const SizedBox(height: AppSpacing.lg),
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
            const SizedBox(height: AppSpacing.sm),
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

class _SliderField extends StatelessWidget {
  const _SliderField({
    required this.label,
    required this.value,
    required this.min,
    required this.max,
    required this.divisions,
    required this.onChanged,
  });

  final String label;
  final double value;
  final double min;
  final double max;
  final int divisions;
  final ValueChanged<double> onChanged;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label, style: AppTypography.labelLg),
            Text(value.round().toString(), style: AppTypography.body),
          ],
        ),
        Slider(
          value: value,
          min: min,
          max: max,
          divisions: divisions,
          onChanged: onChanged,
        ),
      ],
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
      padding: const EdgeInsets.all(AppSpacing.xl2),
      children: [
        const _SectionHeading('About'),
        const SizedBox(height: AppSpacing.xl2),
        infoAsync.when(
          loading: () => const SkeletonBox(width: double.infinity, height: 100),
          error: (_, __) => Text(
            'Unable to read app info',
            style: AppTypography.body.copyWith(color: AppColors.muted),
          ),
          data: (info) => GlassCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('ManhwaManiacs', style: AppTypography.h3),
                const SizedBox(height: AppSpacing.xs),
                Text(
                  'Local-first manga & manhwa reader',
                  style: AppTypography.bodySm.copyWith(color: AppColors.muted),
                ),
                const SizedBox(height: AppSpacing.lg),
                _InfoRow(label: 'Version', value: info.version),
                const SizedBox(height: AppSpacing.sm),
                _InfoRow(label: 'Build', value: info.buildNumber),
              ],
            ),
          ),
        ),
        const SizedBox(height: AppSpacing.lg),
        // Update check
        const _SectionHeading('Updates'),
        const SizedBox(height: AppSpacing.sm),
        // The two channels are not comparable, so neither is their UI: the
        // APK card runs a build-number check the SideStore channel has no
        // equivalent for. See AppVersionInfo.hasUpdate.
        if (channel == AppUpdateChannel.sideStore)
          const _SideStoreUpdateCard()
        else
          const _ApkUpdateCard(),
        const SizedBox(height: AppSpacing.lg),
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
            const Icon(
              Icons.cloud_off_outlined,
              color: AppColors.muted,
              size: 18,
            ),
            const SizedBox(width: AppSpacing.sm),
            Text(
              'Could not check for updates',
              style: AppTypography.body.copyWith(color: AppColors.muted),
            ),
          ],
        ),
      ),
      data: (info) {
        if (info == null) {
          return GlassCard(
            child: Row(
              children: [
                const Icon(
                  Icons.cloud_off_outlined,
                  color: AppColors.muted,
                  size: 18,
                ),
                const SizedBox(width: AppSpacing.sm),
                Text(
                  'Server unreachable',
                  style:
                      AppTypography.body.copyWith(color: AppColors.muted),
                ),
              ],
            ),
          );
        }
        if (!info.hasUpdate) {
          return GlassCard(
            child: Row(
              children: [
                const Icon(
                  Icons.check_circle_outline,
                  color: AppColors.success,
                  size: 18,
                ),
                const SizedBox(width: AppSpacing.sm),
                Text(
                  'Up to date — v${info.localVersion}',
                  style: AppTypography.body,
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
                  const Icon(
                    Icons.system_update_outlined,
                    color: AppColors.primary,
                    size: 18,
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  Text(
                    'Update available',
                    style: AppTypography.labelLg.copyWith(
                      color: AppColors.primary,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.xs),
              Text(
                'v${info.localVersion} → v${info.remoteVersion}',
                style:
                    AppTypography.bodySm.copyWith(color: AppColors.muted),
              ),
              const SizedBox(height: AppSpacing.md),
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
              const Icon(
                Icons.install_mobile_outlined,
                color: AppColors.primary,
                size: 18,
              ),
              const SizedBox(width: AppSpacing.sm),
              Text(
                'Managed by SideStore',
                style: AppTypography.labelLg.copyWith(
                  color: AppColors.primary,
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            'This build is sideloaded. SideStore watches the source below and '
            'offers new builds itself — there is nothing to download here.',
            style: AppTypography.bodySm.copyWith(color: AppColors.muted),
          ),
          const SizedBox(height: AppSpacing.md),
          SelectableText(
            sourceUrl,
            style: AppTypography.bodySm.copyWith(color: AppColors.fg),
          ),
          const SizedBox(height: AppSpacing.sm),
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
          const SizedBox(height: AppSpacing.md),
          Text(
            'A free Apple ID signature lasts 7 days. If the app stops '
            'launching, open SideStore and refresh it — re-signing with the '
            'same Apple ID keeps you signed in here.',
            style: AppTypography.caption.copyWith(color: AppColors.muted),
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
        Text(label, style: AppTypography.body.copyWith(color: AppColors.muted)),
        const SizedBox(width: AppSpacing.md),
        Flexible(
          child: Text(
            value,
            style: AppTypography.labelLg,
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
      padding: const EdgeInsets.all(AppSpacing.xl2),
      children: [
        const _SectionHeading('Diagnostics'),
        const SizedBox(height: AppSpacing.sm),
        GlassCard(
          onTap: () => context.push(Routes.diagnostics),
          child: Row(
            children: [
              const Icon(Icons.speed_rounded, color: AppColors.primary),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Performance & display', style: AppTypography.labelLg),
                    const SizedBox(height: AppSpacing.xxs),
                    Text(
                      // Refresh rate is only a readable/switchable thing on
                      // Android (`flutter_displaymode`); do not advertise it
                      // where the diagnostics screen reports "unsupported".
                      Theme.of(context).platform == TargetPlatform.android
                          ? 'Refresh rate, FPS, frame timing, device info, cache'
                          : 'FPS, frame timing, device info, cache',
                      style: AppTypography.bodySm
                          .copyWith(color: AppColors.muted),
                    ),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right, color: AppColors.muted, size: 18),
            ],
          ),
        ),
        const SizedBox(height: AppSpacing.xl2),
        const _SectionHeading('Reset'),
        const SizedBox(height: AppSpacing.sm),
        GlassCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'Restore reader defaults',
                style: AppTypography.labelLg,
              ),
              const SizedBox(height: AppSpacing.xs),
              Text(
                'Resets direction, fit, brightness, warmth, background, color '
                'mode and refresh rate. Server URL and library are untouched.',
                style: AppTypography.bodySm.copyWith(color: AppColors.muted),
              ),
              const SizedBox(height: AppSpacing.md),
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
