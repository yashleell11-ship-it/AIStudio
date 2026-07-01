import 'package:aistudio_mobile/app/theme/app_colors.dart';
import 'package:aistudio_mobile/app/theme/app_spacing.dart';
import 'package:aistudio_mobile/app/theme/app_typography.dart';
import 'package:aistudio_mobile/core/config/env.dart';
import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/features/downloads/models/download_settings.dart';
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
    _tabController = TabController(length: 2, vsync: this);
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
            Tab(text: 'Server'),
            Tab(text: 'Downloads'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: [
          _ServerSettingsPanel(controller: _apiUrlController),
          const _DownloadSettingsPanel(),
        ],
      ),
    );
  }
}

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
                      content: Text('Server URL saved. Restart the app to apply.'),
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

class _DownloadSettingsPanel extends ConsumerStatefulWidget {
  const _DownloadSettingsPanel();

  @override
  ConsumerState<_DownloadSettingsPanel> createState() => _DownloadSettingsPanelState();
}

class _DownloadSettingsPanelState extends ConsumerState<_DownloadSettingsPanel> {
  DownloadSettings? _draft;
  var _saving = false;

  @override
  Widget build(BuildContext context) {
    final settingsAsync = ref.watch(downloadSettingsProvider);

    return settingsAsync.when(
      loading: () => const Padding(
        padding: EdgeInsets.all(AppSpacing.xl2),
        child: SkeletonBox(width: double.infinity, height: 240),
      ),
      error: (error, _) => Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              error is AppError ? error.userMessage : 'Failed to load settings.',
              style: AppTypography.body.copyWith(color: AppColors.danger),
            ),
            const SizedBox(height: AppSpacing.lg),
            FilledButton(
              onPressed: () => ref.invalidate(downloadSettingsProvider),
              child: const Text('Retry'),
            ),
          ],
        ),
      ),
      data: (settings) {
        _draft ??= settings;
        final draft = _draft!;

        return ListView(
          padding: const EdgeInsets.all(AppSpacing.xl2),
          children: [
            Text('Download queue', style: AppTypography.h3),
            const SizedBox(height: AppSpacing.sm),
            Text(
              '${settings.activeDownloadCount} active downloads',
              style: AppTypography.body.copyWith(color: AppColors.muted),
            ),
            const SizedBox(height: AppSpacing.xl2),
            GlassCard(
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
                ],
              ),
            ),
            const SizedBox(height: AppSpacing.xl2),
            FilledButton(
              onPressed: _saving
                  ? null
                  : () async {
                      setState(() => _saving = true);
                      final error = await ref
                          .read(settingsActionsProvider)
                          .saveDownloadSettings(draft);
                      if (!mounted) return;
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
