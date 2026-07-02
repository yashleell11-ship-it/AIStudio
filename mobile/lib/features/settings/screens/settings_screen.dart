import 'package:aistudio_mobile/app/theme/app_colors.dart';
import 'package:aistudio_mobile/app/theme/app_spacing.dart';
import 'package:aistudio_mobile/app/theme/app_typography.dart';
import 'package:aistudio_mobile/core/config/env.dart';
import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/features/downloads/models/download_settings.dart';
import 'package:aistudio_mobile/features/settings/models/reader_defaults.dart';
import 'package:aistudio_mobile/features/settings/providers/settings_provider.dart';
import 'package:aistudio_mobile/shared/widgets/glass_card.dart';
import 'package:aistudio_mobile/shared/widgets/skeleton_box.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

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
    _tabController = TabController(length: 3, vsync: this);
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
        bottom: TabBar(
          controller: _tabController,
          tabs: const [
            Tab(text: 'General'),
            Tab(text: 'Server'),
            Tab(text: 'About'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: [
          const _GeneralSettingsPanel(),
          _ServerSettingsPanel(controller: _apiUrlController),
          const _AboutPanel(),
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
        _SectionHeading('Default reader preferences'),
        SizedBox(height: AppSpacing.sm),
        _ReaderDefaultsSection(),
        SizedBox(height: AppSpacing.xl2),
        _SectionHeading('Download preferences'),
        SizedBox(height: AppSpacing.sm),
        _DownloadPreferencesSection(),
        SizedBox(height: AppSpacing.xl2),
        _SectionHeading('Cache'),
        SizedBox(height: AppSpacing.sm),
        _CacheSection(),
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
            .map((lang) => DropdownMenuItem(value: lang, child: Text(lang.label)))
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
            onSelectionChanged: (selection) => notifier.setDirection(selection.first),
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
            onSelectionChanged: (selection) => notifier.setFitMode(selection.first),
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
              subtitle: const Text('Only download chapters while connected to Wi-Fi'),
              value: wifiOnly,
              onChanged: (value) =>
                  ref.read(wifiOnlyDownloadsProvider.notifier).setEnabled(value),
            ),
          ),
        ),
        const SizedBox(height: AppSpacing.lg),
        settingsAsync.when(
          loading: () => const SkeletonBox(width: double.infinity, height: 180),
          error: (error, _) => Text(
            error is AppError ? error.userMessage : 'Failed to load download settings.',
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
                                const SnackBar(content: Text('Download settings saved.')),
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

class _CacheSection extends ConsumerWidget {
  const _CacheSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final usageAsync = ref.watch(cacheUsageProvider);

    return GlassCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Image cache usage', style: AppTypography.labelLg),
          const SizedBox(height: AppSpacing.xs),
          usageAsync.when(
            loading: () => const SkeletonBox(width: 120, height: 20),
            error: (_, __) => Text(
              'Unable to read cache size',
              style: AppTypography.body.copyWith(color: AppColors.muted),
            ),
            data: (bytes) => Text(
              _formatBytes(bytes),
              style: AppTypography.body.copyWith(color: AppColors.muted),
            ),
          ),
          const SizedBox(height: AppSpacing.lg),
          OutlinedButton(
            onPressed: () async {
              await ref.read(settingsActionsProvider).clearImageCache();
              if (context.mounted) {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Image cache cleared.')),
                );
              }
            },
            child: const Text('Clear image cache'),
          ),
          const SizedBox(height: AppSpacing.sm),
          OutlinedButton(
            onPressed: () {
              ref.read(settingsActionsProvider).clearMetadataCache();
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Metadata cache cleared.')),
              );
            },
            child: const Text('Clear metadata cache'),
          ),
        ],
      ),
    );
  }

  String _formatBytes(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
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
              'Configure the AIStudio backend URL for this device.',
              style: AppTypography.body.copyWith(color: AppColors.muted),
            ),
            const SizedBox(height: AppSpacing.xl2),
            TextField(
              controller: controller,
              decoration: InputDecoration(
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
                Text('AIStudio', style: AppTypography.h3),
                const SizedBox(height: AppSpacing.xs),
                Text(
                  'Local-first manga & manhwa reader',
                  style: AppTypography.bodySm.copyWith(color: AppColors.muted),
                ),
                const SizedBox(height: AppSpacing.lg),
                _InfoRow(label: 'App name', value: info.appName),
                const SizedBox(height: AppSpacing.sm),
                _InfoRow(label: 'App version', value: info.version),
                const SizedBox(height: AppSpacing.sm),
                _InfoRow(label: 'Build number', value: info.buildNumber),
              ],
            ),
          ),
        ),
        const SizedBox(height: AppSpacing.lg),
        OutlinedButton(
          onPressed: () {
            final info = infoAsync.valueOrNull;
            showLicensePage(
              context: context,
              applicationName: info?.appName ?? 'AIStudio',
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
      children: [
        Text(label, style: AppTypography.body.copyWith(color: AppColors.muted)),
        Text(value, style: AppTypography.labelLg),
      ],
    );
  }
}
