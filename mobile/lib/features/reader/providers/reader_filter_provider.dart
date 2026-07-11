import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';

/// Page backdrop shown behind letterboxed pages while reading.
enum ReaderBackground {
  dark,
  black,
  white;

  String get label => switch (this) {
        ReaderBackground.dark => 'Dark',
        ReaderBackground.black => 'AMOLED',
        ReaderBackground.white => 'Paper',
      };

  Color get color => switch (this) {
        ReaderBackground.dark => AppColors.bg,
        ReaderBackground.black => const Color(0xFF000000),
        ReaderBackground.white => const Color(0xFFF5F1E8),
      };

  static ReaderBackground fromStorageValue(String? value) =>
      ReaderBackground.values.firstWhere(
        (b) => b.name == value,
        orElse: () => ReaderBackground.dark,
      );
}

/// Colour treatment applied to the page content itself (distinct from the
/// [ReaderBackground] letterbox). Implemented as a single [ColorFilter] wrapped
/// around the page list, so [ReaderColorMode.normal] adds zero cost.
enum ReaderColorMode {
  normal,
  sepia,
  grayscale;

  String get label => switch (this) {
        ReaderColorMode.normal => 'Normal',
        ReaderColorMode.sepia => 'Sepia',
        ReaderColorMode.grayscale => 'Gray',
      };

  /// A 4×5 colour matrix, or ``null`` for [normal] (no filtering).
  ColorFilter? get colorFilter => switch (this) {
        ReaderColorMode.normal => null,
        // Classic sepia tone matrix.
        ReaderColorMode.sepia => const ColorFilter.matrix(<double>[
            0.393, 0.769, 0.189, 0, 0, //
            0.349, 0.686, 0.168, 0, 0, //
            0.272, 0.534, 0.131, 0, 0, //
            0, 0, 0, 1, 0, //
          ]),
        // Luminance-preserving desaturation.
        ReaderColorMode.grayscale => const ColorFilter.matrix(<double>[
            0.2126, 0.7152, 0.0722, 0, 0, //
            0.2126, 0.7152, 0.0722, 0, 0, //
            0.2126, 0.7152, 0.0722, 0, 0, //
            0, 0, 0, 1, 0, //
          ]),
      };

  static ReaderColorMode fromStorageValue(String? value) =>
      ReaderColorMode.values.firstWhere(
        (m) => m.name == value,
        orElse: () => ReaderColorMode.normal,
      );
}

/// Runtime reader display filter — screen dimming, a warm (blue-light) tint and
/// the page backdrop. Kept separate from [readerDefaultsProvider] so adjusting
/// brightness/warmth never rebuilds the virtualized page list.
class ReaderFilter {
  const ReaderFilter({
    this.brightness = 1.0,
    this.warmth = 0.0,
    this.background = ReaderBackground.dark,
    this.colorMode = ReaderColorMode.normal,
  });

  /// 0.2 (dim) … 1.0 (full). Values below 1 darken the page via an overlay,
  /// letting the reader go dimmer than the OS minimum without touching
  /// system brightness.
  final double brightness;

  /// 0.0 (off) … 1.0 (warmest). Amber overlay to cut blue light at night.
  final double warmth;

  final ReaderBackground background;

  /// Sepia / grayscale tone applied to page content.
  final ReaderColorMode colorMode;

  /// Dim overlay alpha (0–255). Caps at ~0.72 so the page never fully blacks out.
  int get dimAlpha => ((1.0 - brightness).clamp(0.0, 1.0) * 184).round();

  /// Warmth overlay alpha (0–255).
  int get warmthAlpha => (warmth.clamp(0.0, 1.0) * 92).round();

  bool get hasOverlay => dimAlpha > 0 || warmthAlpha > 0;

  ReaderFilter copyWith({
    double? brightness,
    double? warmth,
    ReaderBackground? background,
    ReaderColorMode? colorMode,
  }) =>
      ReaderFilter(
        brightness: brightness ?? this.brightness,
        warmth: warmth ?? this.warmth,
        background: background ?? this.background,
        colorMode: colorMode ?? this.colorMode,
      );
}

class ReaderFilterController extends Notifier<ReaderFilter> {
  @override
  ReaderFilter build() {
    final prefs = ref.watch(preferencesProvider);
    return ReaderFilter(
      brightness: prefs.readerBrightness.clamp(0.2, 1.0),
      warmth: prefs.readerWarmth.clamp(0.0, 1.0),
      background: ReaderBackground.fromStorageValue(prefs.readerBackground),
      colorMode: ReaderColorMode.fromStorageValue(prefs.readerColorMode),
    );
  }

  Future<void> setBrightness(double value) async {
    final clamped = value.clamp(0.2, 1.0);
    state = state.copyWith(brightness: clamped);
    await ref.read(preferencesProvider).setReaderBrightness(clamped);
  }

  Future<void> setWarmth(double value) async {
    final clamped = value.clamp(0.0, 1.0);
    state = state.copyWith(warmth: clamped);
    await ref.read(preferencesProvider).setReaderWarmth(clamped);
  }

  Future<void> setBackground(ReaderBackground background) async {
    state = state.copyWith(background: background);
    await ref.read(preferencesProvider).setReaderBackground(background.name);
  }

  Future<void> setColorMode(ReaderColorMode mode) async {
    state = state.copyWith(colorMode: mode);
    await ref.read(preferencesProvider).setReaderColorMode(mode.name);
  }
}

final readerFilterProvider =
    NotifierProvider<ReaderFilterController, ReaderFilter>(
  ReaderFilterController.new,
);

/// Full-screen, non-interactive dim + warmth overlay. Watches only the filter
/// provider, so brightness/warmth changes repaint just this layer.
class ReaderFilterOverlay extends ConsumerWidget {
  const ReaderFilterOverlay({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final filter = ref.watch(
      readerFilterProvider.select((f) => (f.dimAlpha, f.warmthAlpha)),
    );
    final (dimAlpha, warmthAlpha) = filter;
    if (dimAlpha == 0 && warmthAlpha == 0) return const SizedBox.shrink();

    return Positioned.fill(
      child: IgnorePointer(
        child: RepaintBoundary(
          child: Stack(
            children: [
              if (dimAlpha > 0)
                Positioned.fill(
                  child: ColoredBox(color: Colors.black.withAlpha(dimAlpha)),
                ),
              if (warmthAlpha > 0)
                Positioned.fill(
                  child: ColoredBox(
                    color: const Color(0xFFFF8A00).withAlpha(warmthAlpha),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
