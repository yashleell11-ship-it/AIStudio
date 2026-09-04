import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/core/diagnostics/performance_monitor.dart';
import 'package:manhwamaniacs/features/reader/utils/reader_display_mode.dart';
import 'package:manhwamaniacs/features/settings/providers/settings_provider.dart';
import 'package:manhwamaniacs/shared/widgets/glass_card.dart';

/// Developer diagnostics: live rendering performance, display/refresh-rate
/// verification, device details and image-cache usage. Reached from Settings →
/// Debug. Starting the performance monitor here (and stopping on dispose) keeps
/// the frame-timing callback registered only while this screen is visible.
class DiagnosticsScreen extends ConsumerStatefulWidget {
  const DiagnosticsScreen({super.key});

  @override
  ConsumerState<DiagnosticsScreen> createState() => _DiagnosticsScreenState();
}

class _DiagnosticsScreenState extends ConsumerState<DiagnosticsScreen> {
  PerformanceMonitor? _monitor;
  DisplayModeInfo? _display;
  bool _loadingDisplay = true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final monitor = ref.read(performanceMonitorProvider);
      monitor.start();
      _monitor = monitor;
      _loadDisplay();
    });
  }

  Future<void> _loadDisplay() async {
    final mode = ref.read(readerDisplayModeProvider);
    final info = await mode.describe();
    if (!mounted) return;
    setState(() {
      _display = info;
      _loadingDisplay = false;
      final rate = info.activeRefreshRate;
      if (rate > 0) _monitor?.setTargetRefreshRate(rate);
    });
  }

  @override
  void dispose() {
    _monitor?.stop();
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
              context.canPop() ? context.pop() : context.go(Routes.settings),
        ),
        title: const Text('Diagnostics'),
      ),
      body: ListView(
        padding: const EdgeInsets.all(AppSpacing.xl2),
        children: [
          const _SectionHeading('Rendering performance'),
          const SizedBox(height: AppSpacing.sm),
          _PerformanceCard(monitor: _monitor),
          const SizedBox(height: AppSpacing.xl2),
          const _SectionHeading('Display'),
          const SizedBox(height: AppSpacing.sm),
          _DisplayCard(info: _display, loading: _loadingDisplay),
          const SizedBox(height: AppSpacing.xl2),
          const _SectionHeading('Device'),
          const SizedBox(height: AppSpacing.sm),
          _DeviceCard(ref: ref),
          const SizedBox(height: AppSpacing.xl2),
          const _SectionHeading('Image cache'),
          const SizedBox(height: AppSpacing.sm),
          const _ImageCacheCard(),
        ],
      ),
    );
  }
}

/// Premium section eyebrow: warm amber accent bar beside an uppercase Syne
/// label, matching the Settings screen section groups.
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
              color: context.colors.primary,
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
              color: context.colors.fg,
            ),
          ),
        ],
      ),
    );
  }
}

/// Live FPS / frame-timing readout. Rebuilds only itself, driven by the
/// throttled [PerformanceMonitor] notifications (~2×/sec) so it never adds jank.
class _PerformanceCard extends StatelessWidget {
  const _PerformanceCard({required this.monitor});

  final PerformanceMonitor? monitor;

  @override
  Widget build(BuildContext context) {
    final m = monitor;
    if (m == null) {
      return const GlassCard(
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.md),
          child: Text('Starting profiler…'),
        ),
      );
    }
    return AnimatedBuilder(
      animation: m,
      builder: (context, _) {
        final s = m.snapshot;
        if (!s.hasData) {
          return const GlassCard(
            child: Text('Collecting frames… scroll a screen to sample.'),
          );
        }
        final jankColor = s.jankPercent < 5
            ? context.colors.success
            : s.jankPercent < 15
                ? context.colors.warning
                : context.colors.danger;
        return GlassCard(
          child: Column(
            children: [
              Row(
                children: [
                  Expanded(
                    child: _Metric(
                      label: 'FPS',
                      value: s.fps.toStringAsFixed(0),
                      accent: context.colors.primary,
                    ),
                  ),
                  Expanded(
                    child: _Metric(
                      label: 'Jank',
                      value: '${s.jankPercent.toStringAsFixed(1)}%',
                      accent: jankColor,
                    ),
                  ),
                  Expanded(
                    child: _Metric(
                      label: 'Worst',
                      value: '${s.worstFrameMs.toStringAsFixed(1)}ms',
                      accent: context.colors.accent,
                    ),
                  ),
                ],
              ),
              const Divider(height: AppSpacing.xl2),
              _InfoRow(
                label: 'Avg frame time',
                value: '${s.avgFrameMs.toStringAsFixed(2)} ms',
              ),
              _InfoRow(
                label: 'CPU (build)',
                value: '${s.avgBuildMs.toStringAsFixed(2)} ms',
              ),
              _InfoRow(
                label: 'GPU (raster)',
                value: '${s.avgRasterMs.toStringAsFixed(2)} ms',
              ),
              _InfoRow(label: 'Samples', value: '${s.sampleCount}'),
            ],
          ),
        );
      },
    );
  }
}

class _DisplayCard extends StatelessWidget {
  const _DisplayCard({required this.info, required this.loading});

  final DisplayModeInfo? info;
  final bool loading;

  @override
  Widget build(BuildContext context) {
    if (loading) {
      return const GlassCard(child: Text('Reading display modes…'));
    }
    final i = info;
    if (i == null || !i.supported) {
      return GlassCard(
        child: Text(
          'Switchable display modes are only available on Android devices.',
          style: TextStyle(color: context.colors.muted),
        ),
      );
    }
    return GlassCard(
      child: Column(
        children: [
          _InfoRow(
            label: 'Current refresh rate',
            value: '${i.activeRefreshRate.toStringAsFixed(1)} Hz',
          ),
          _InfoRow(
            label: 'Device capability',
            value: '${i.maxRefreshRate.toStringAsFixed(1)} Hz max',
          ),
          _InfoRow(
            label: 'Active resolution',
            value: '${i.activeWidth} × ${i.activeHeight}',
          ),
        ],
      ),
    );
  }
}

class _DeviceCard extends StatelessWidget {
  const _DeviceCard({required this.ref});

  final WidgetRef ref;

  @override
  Widget build(BuildContext context) {
    final infoAsync = ref.watch(packageInfoProvider);
    final mq = MediaQuery.of(context);
    return GlassCard(
      child: Column(
        children: [
          _InfoRow(
            label: 'Platform',
            value: '${_platformName()} (${_osVersion()})',
          ),
          _InfoRow(label: 'CPU cores', value: '${Platform.numberOfProcessors}'),
          _InfoRow(
            label: 'Screen',
            value:
                '${mq.size.width.toStringAsFixed(0)} × ${mq.size.height.toStringAsFixed(0)} @ ${mq.devicePixelRatio.toStringAsFixed(1)}x',
          ),
          infoAsync.when(
            loading: () => const _InfoRow(label: 'App version', value: '…'),
            error: (_, __) =>
                const _InfoRow(label: 'App version', value: 'unknown'),
            data: (i) => _InfoRow(
              label: 'App version',
              value: 'v${i.version} (${i.buildNumber})',
            ),
          ),
          _InfoRow(label: 'Build mode', value: _buildMode()),
        ],
      ),
    );
  }

  String _platformName() {
    if (kIsWeb) return 'Web';
    if (Platform.isAndroid) return 'Android';
    if (Platform.isIOS) return 'iOS';
    return Platform.operatingSystem;
  }

  String _osVersion() {
    if (kIsWeb) return 'browser';
    // operatingSystemVersion can be verbose; keep the first segment only.
    final raw = Platform.operatingSystemVersion;
    return raw.length > 40 ? '${raw.substring(0, 40)}…' : raw;
  }

  String _buildMode() {
    if (kDebugMode) return 'debug';
    if (kProfileMode) return 'profile';
    return 'release';
  }
}

class _ImageCacheCard extends StatelessWidget {
  const _ImageCacheCard();

  @override
  Widget build(BuildContext context) {
    final cache = PaintingBinding.instance.imageCache;
    return GlassCard(
      child: Column(
        children: [
          _InfoRow(
            label: 'Live images',
            value: '${cache.liveImageCount}',
          ),
          _InfoRow(
            label: 'Cached images',
            value: '${cache.currentSize} / ${cache.maximumSize}',
          ),
          _InfoRow(
            label: 'Memory used',
            value:
                '${_mb(cache.currentSizeBytes)} / ${_mb(cache.maximumSizeBytes)}',
          ),
        ],
      ),
    );
  }

  String _mb(int bytes) => '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
}

class _Metric extends StatelessWidget {
  const _Metric({
    required this.label,
    required this.value,
    required this.accent,
  });

  final String label;
  final String value;
  final Color accent;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(
          value,
          style: AppTypography.h2.copyWith(color: accent),
        ),
        const SizedBox(height: AppSpacing.xxs),
        Text(
          label.toUpperCase(),
          style: AppTypography.labelSm.copyWith(
            color: context.colors.muted,
            letterSpacing: 1,
          ),
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
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: AppTypography.body.copyWith(color: context.colors.muted),
          ),
          const SizedBox(width: AppSpacing.md),
          Flexible(
            child: Text(
              value,
              style: AppTypography.labelLg,
              textAlign: TextAlign.right,
            ),
          ),
        ],
      ),
    );
  }
}
