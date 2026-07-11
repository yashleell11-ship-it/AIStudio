import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/core/config/env.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/downloads/models/download_settings.dart';
import 'package:manhwamaniacs/features/reader/providers/reader_filter_provider.dart';
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

class _SectionHeading extends StatelessWidget {
  const _SectionHeading(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Text(text, style: AppTypography.h3);
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

class _ReaderDefaultsSection extends ConsumerWidget {
  const _ReaderDefaultsSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final defaults = ref.watch(readerDefaultsProvider);
    final notifier = ref.read(readerDefaultsProvider.notifier);

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
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Volume key navigation'),
                  subtitle: const Text(
                    'Turn pages with the volume buttons (Android)',
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
          error: (error, _) => Text(
            error is AppError
                ? error.userMessage
                : 'Failed to load download settings.',
            style: AppTypography.body.copyWith(color: AppColors.danger),
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
            Text(
              'Server connection',
              style: AppTypography.h3,
            ),
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
                controller.text = Env.defaultApiUrl;
                if (context.mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('Reset to default URL.')),
                  );
                }
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
    final updateAsync = ref.watch(appUpdateProvider);

    return ListView(
      padding: const EdgeInsets.all(AppSpacing.xl2),
      children: [
        Text('About', style: AppTypography.h3),
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
        Text('Updates', style: AppTypography.h3),
        const SizedBox(height: AppSpacing.sm),
        updateAsync.when(
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
                        color: AppColors.violet400,
                        size: 18,
                      ),
                      const SizedBox(width: AppSpacing.sm),
                      Text(
                        'Update available',
                        style: AppTypography.labelLg.copyWith(
                          color: AppColors.violet400,
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
        ),
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
        Text('Diagnostics', style: AppTypography.h3),
        const SizedBox(height: AppSpacing.sm),
        GlassCard(
          onTap: () => context.push(Routes.diagnostics),
          child: Row(
            children: [
              const Icon(Icons.speed_rounded, color: AppColors.violet400),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Performance & display', style: AppTypography.labelLg),
                    const SizedBox(height: AppSpacing.xxs),
                    Text(
                      'Refresh rate, FPS, frame timing, device info, cache',
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
        Text('Reset', style: AppTypography.h3),
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
