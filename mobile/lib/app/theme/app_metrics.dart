import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';

/// The **shape** half of the design system, sibling to `AppPalette`'s colour
/// half.
///
/// A theme answers "what colour is it"; a preset answers "what shape is it" —
/// density, corner radius, whether a surface is frosted glass or solid ink,
/// how big the type steps are, how a library lays itself out, how much motion
/// and how much reader furniture. The two axes are deliberately orthogonal:
/// **[AppMetrics] holds no [Color] anywhere**, and `AppPalette` holds no size,
/// so Nord + Compact and Nord + Editorial are both real, working combinations.
/// `test/app/theme/preset_orthogonality_test.dart` enforces that, so a colour
/// cannot creep in later.
///
/// Like the palette this rides on [ThemeData.extensions], which is the whole
/// live-apply mechanism: a `context.space.lg` read registers a Theme
/// dependency, so changing preset rebuilds exactly the widgets that measured
/// with it — no restart, and [MaterialApp]'s own [AnimatedTheme] tweens the
/// numbers through [lerp] on the way.
@immutable
class AppMetrics extends ThemeExtension<AppMetrics> {
  const AppMetrics({
    required this.id,
    required this.name,
    required this.description,
    required this.space,
    required this.radii,
    required this.strokes,
    required this.surfaces,
    required this.text,
    required this.layout,
    required this.motion,
    required this.reader,
  });

  /// Stable identifier persisted in preferences — never rename a shipped id.
  final String id;

  /// Human-readable name shown in the preset picker.
  final String name;

  /// One line explaining the position this preset takes, shown under [name].
  final String description;

  final AppSpacingScale space;
  final AppRadiusScale radii;
  final AppStrokes strokes;
  final AppSurfaceStyle surfaces;
  final AppTextStyles text;
  final AppLayoutDefaults layout;
  final AppMotion motion;
  final AppReaderChrome reader;

  @override
  AppMetrics copyWith({
    String? id,
    String? name,
    String? description,
    AppSpacingScale? space,
    AppRadiusScale? radii,
    AppStrokes? strokes,
    AppSurfaceStyle? surfaces,
    AppTextStyles? text,
    AppLayoutDefaults? layout,
    AppMotion? motion,
    AppReaderChrome? reader,
  }) {
    return AppMetrics(
      id: id ?? this.id,
      name: name ?? this.name,
      description: description ?? this.description,
      space: space ?? this.space,
      radii: radii ?? this.radii,
      strokes: strokes ?? this.strokes,
      surfaces: surfaces ?? this.surfaces,
      text: text ?? this.text,
      layout: layout ?? this.layout,
      motion: motion ?? this.motion,
      reader: reader ?? this.reader,
    );
  }

  @override
  AppMetrics lerp(ThemeExtension<AppMetrics>? other, double t) {
    if (other is! AppMetrics) return this;
    // Continuous tokens (spacing, radii, stroke widths, type metrics) tween so
    // the switch reads as the layout settling rather than snapping. Discrete
    // ones (layout mode, reader chrome) have no meaningful in-between, so they
    // flip with the identity at the midpoint — the same rule AppPalette uses
    // for id/name/brightness.
    final target = t < 0.5 ? this : other;
    return AppMetrics(
      id: target.id,
      name: target.name,
      description: target.description,
      space: AppSpacingScale.lerp(space, other.space, t),
      radii: AppRadiusScale.lerp(radii, other.radii, t),
      strokes: AppStrokes.lerp(strokes, other.strokes, t),
      surfaces: AppSurfaceStyle.lerp(surfaces, other.surfaces, t),
      text: AppTextStyles.lerp(text, other.text, t),
      layout: target.layout,
      motion: AppMotion.lerp(motion, other.motion, t),
      reader: target.reader,
    );
  }
}

// ── Spacing ──────────────────────────────────────────────────────────────────

/// The app's spacing rhythm, step by step.
///
/// Every step is stated explicitly rather than derived from one multiplier:
/// presets differ in *rhythm*, not just size. Compact leaves the 2px hairline
/// gaps alone (they are already minimal) and takes its density out of the
/// large steps, where the page padding actually lives; Editorial does the
/// reverse and widens only the margins.
@immutable
class AppSpacingScale {
  const AppSpacingScale({
    required this.xxs,
    required this.xs,
    required this.sm,
    required this.md,
    required this.lg,
    required this.xl,
    required this.xl2,
    required this.xl3,
    required this.xl4,
    required this.xl5,
    required this.xl6,
    required this.xl7,
  });

  final double xxs;
  final double xs;
  final double sm;
  final double md;
  final double lg;
  final double xl;
  final double xl2;
  final double xl3;
  final double xl4;
  final double xl5;
  final double xl6;
  final double xl7;

  /// Every step in ascending order — used by the preset tests, which is why
  /// this is a list and not twelve assertions.
  List<double> get steps =>
      [xxs, xs, sm, md, lg, xl, xl2, xl3, xl4, xl5, xl6, xl7];

  static AppSpacingScale lerp(AppSpacingScale a, AppSpacingScale b, double t) {
    double l(double x, double y) => x + (y - x) * t;
    return AppSpacingScale(
      xxs: l(a.xxs, b.xxs),
      xs: l(a.xs, b.xs),
      sm: l(a.sm, b.sm),
      md: l(a.md, b.md),
      lg: l(a.lg, b.lg),
      xl: l(a.xl, b.xl),
      xl2: l(a.xl2, b.xl2),
      xl3: l(a.xl3, b.xl3),
      xl4: l(a.xl4, b.xl4),
      xl5: l(a.xl5, b.xl5),
      xl6: l(a.xl6, b.xl6),
      xl7: l(a.xl7, b.xl7),
    );
  }
}

// ── Corner radius ────────────────────────────────────────────────────────────

/// Corner radii, from hairline chips to hero cards.
///
/// [pill] and [full] deliberately do **not** vary across presets. They are the
/// "clamp to fully round" tokens — avatars, progress rails, the accent bar
/// beside a section heading — and a circle that stops being a circle reads as
/// a bug, not as a design position. A preset expresses "crisp" through the
/// named steps ([md] … [xl4]) and through [AppStrokes], not by squaring off
/// the app's circles.
@immutable
class AppRadiusScale {
  const AppRadiusScale({
    required this.xs,
    required this.sm,
    required this.md,
    required this.lg,
    required this.xl,
    required this.xl2,
    required this.xl3,
    required this.xl4,
  });

  final double xs;
  final double sm;
  final double md;
  final double lg;
  final double xl;
  final double xl2;
  final double xl3;
  final double xl4;

  /// Fully rounded pill — buttons, chips, tags. Constant across presets.
  double get pill => 999;

  /// Fully rounded — circles and rails. Constant across presets.
  double get full => 9999;

  List<double> get steps => [xs, sm, md, lg, xl, xl2, xl3, xl4];

  static AppRadiusScale lerp(AppRadiusScale a, AppRadiusScale b, double t) {
    double l(double x, double y) => x + (y - x) * t;
    return AppRadiusScale(
      xs: l(a.xs, b.xs),
      sm: l(a.sm, b.sm),
      md: l(a.md, b.md),
      lg: l(a.lg, b.lg),
      xl: l(a.xl, b.xl),
      xl2: l(a.xl2, b.xl2),
      xl3: l(a.xl3, b.xl3),
      xl4: l(a.xl4, b.xl4),
    );
  }
}

// ── Stroke weights ───────────────────────────────────────────────────────────

/// Border and divider weights. Colour comes from the palette; only the
/// thickness is a preset's business.
@immutable
class AppStrokes {
  const AppStrokes({
    required this.border,
    required this.focus,
    required this.divider,
  });

  /// Weight of a resting border on a card, panel or input.
  final double border;

  /// Weight of the focused-input / selected-item border.
  final double focus;

  /// Weight of a rule between rows.
  final double divider;

  static AppStrokes lerp(AppStrokes a, AppStrokes b, double t) {
    double l(double x, double y) => x + (y - x) * t;
    return AppStrokes(
      border: l(a.border, b.border),
      focus: l(a.focus, b.focus),
      divider: l(a.divider, b.divider),
    );
  }
}

// ── Surface treatment ────────────────────────────────────────────────────────

/// How a raised surface is built: frosted glass over the content behind it, or
/// solid ink that occludes it.
enum SurfaceTreatment {
  /// Backdrop blur behind a translucent fill — the shipped Signature look.
  glass,

  /// Opaque fill, no blur, no gradient. Cheaper to paint and calmer to read.
  solid,
}

/// The single most visible axis a preset controls.
///
/// [blurSigma] of zero means the [BackdropFilter] is skipped entirely rather
/// than run with a no-op filter — a blur of 0 still costs a saveLayer, and
/// "faster to paint" is half of what the solid presets are for.
@immutable
class AppSurfaceStyle {
  const AppSurfaceStyle({
    required this.treatment,
    required this.blurSigma,
    required this.chromeBlurSigma,
    required this.panelOpacity,
    required this.chromeOpacity,
    required this.cardOpacity,
    required this.gradientCards,
    required this.glowAlpha,
    required this.cardBorderIsStrong,
  });

  final SurfaceTreatment treatment;

  /// Backdrop blur radius for panels; 0 skips the filter.
  final double blurSigma;

  /// Backdrop blur radius for *floating chrome* — the bottom nav, the reader's
  /// bars. Stated separately from [blurSigma] rather than derived from it
  /// because chrome hovers over arbitrary artwork and has always carried a
  /// slightly heavier blur than a panel resting on the page background.
  final double chromeBlurSigma;

  /// Alpha of a `GlassPanel`'s fill over the content behind it.
  final double panelOpacity;

  /// Alpha of floating chrome's fill. Higher than [panelOpacity]: a nav bar
  /// has to stay readable over a cover, where a panel only sits on the page.
  final double chromeOpacity;

  /// Alpha of a `GlassCard`'s fill.
  final double cardOpacity;

  /// Whether cards carry the top-to-bottom highlight gradient.
  final bool gradientCards;

  /// Strength (0–255) of the ambient glow behind a card that asks for one; 0
  /// drops the [BoxShadow] entirely.
  final double glowAlpha;

  /// Whether a card's edge is the palette's full-strength `border` (a crisp
  /// hairline you are meant to see) rather than the softer `glassEdge`.
  final bool cardBorderIsStrong;

  /// True only when a backdrop blur is actually worth the saveLayer.
  bool get isGlass => treatment == SurfaceTreatment.glass && blurSigma > 0;

  /// Whether floating chrome earns a blur.
  bool get isChromeGlass =>
      treatment == SurfaceTreatment.glass && chromeBlurSigma > 0;

  static AppSurfaceStyle lerp(
    AppSurfaceStyle a,
    AppSurfaceStyle b,
    double t,
  ) {
    double l(double x, double y) => x + (y - x) * t;
    final target = t < 0.5 ? a : b;
    return AppSurfaceStyle(
      treatment: target.treatment,
      blurSigma: l(a.blurSigma, b.blurSigma),
      chromeBlurSigma: l(a.chromeBlurSigma, b.chromeBlurSigma),
      panelOpacity: l(a.panelOpacity, b.panelOpacity),
      chromeOpacity: l(a.chromeOpacity, b.chromeOpacity),
      cardOpacity: l(a.cardOpacity, b.cardOpacity),
      gradientCards: target.gradientCards,
      glowAlpha: l(a.glowAlpha, b.glowAlpha),
      cardBorderIsStrong: target.cardBorderIsStrong,
    );
  }
}

// ── Typography ───────────────────────────────────────────────────────────────

/// Which face a preset gives its headings.
enum AppHeadingFace {
  /// Syne — the shipped display face.
  display,

  /// DM Sans — headings in the body face, which reads denser and quieter.
  body,

  /// A system serif, for the typography-led preset.
  serif,
}

/// Long-form serif stack for [AppHeadingFace.serif].
///
/// **System faces only**, for the same reason the novel reader uses system
/// faces (`features/novels/models/novel_typography.dart`): the app bundles no
/// serif and must never fetch one at runtime, so a preset that wants serif
/// headings asks the phone for the best book face it already has. Stated here
/// rather than imported from the novels feature because `app/theme` sits below
/// every feature and must not depend on one.
const List<String> kPresetSerifStack = <String>[
  'Iowan Old Style',
  'Charter',
  'Bitstream Charter',
  'Georgia',
  'Palatino',
  'Noto Serif',
  'Tinos',
  'Times New Roman',
  'serif',
];

/// The smallest font size any preset may produce.
///
/// Density is allowed to buy rows; it is not allowed to buy illegibility, and
/// the contrast floors the palette suite enforces assume text a reader can
/// actually resolve at all. `preset_metrics_test.dart` asserts this holds for
/// every style of every preset.
const double kMinPresetFontSize = 11;

/// The knobs a preset turns on the shipped [AppTypography] scale.
@immutable
class AppTypeScale {
  const AppTypeScale({
    this.sizeScale = 1.0,
    this.lineHeightScale = 1.0,
    this.headingFace = AppHeadingFace.display,
    this.headingTracking = 0,
    this.headingWeight,
  });

  /// Multiplier on every step's font size, floored at [kMinPresetFontSize].
  final double sizeScale;

  /// Multiplier on every step's line height.
  final double lineHeightScale;

  final AppHeadingFace headingFace;

  /// Letter-spacing added to heading styles only.
  final double headingTracking;

  /// Overrides heading weight; null keeps the shipped weight.
  final FontWeight? headingWeight;
}

/// The resolved text styles for a preset — same names as [AppTypography], so a
/// call site migrates by swapping the receiver and nothing else.
@immutable
class AppTextStyles {
  const AppTextStyles({
    required this.displayLg,
    required this.displayMd,
    required this.h1,
    required this.h2,
    required this.h3,
    required this.h4,
    required this.bodyLg,
    required this.body,
    required this.bodySm,
    required this.labelLg,
    required this.label,
    required this.labelSm,
    required this.caption,
    required this.mono,
  });

  /// Applies [scale] to the shipped [AppTypography] steps.
  ///
  /// The serif face lands on the display styles and h1–h3 only: h4 is used
  /// throughout the app as a small section label rather than as prose
  /// furniture, and setting it in a book face makes plain lists read as
  /// headings.
  factory AppTextStyles.resolve(AppTypeScale scale) {
    TextStyle sized(TextStyle base) => _sized(base, scale);
    TextStyle heading(TextStyle base, {bool serifEligible = true}) =>
        _heading(base, scale, serifEligible: serifEligible);

    return AppTextStyles(
      displayLg: heading(AppTypography.displayLg),
      displayMd: heading(AppTypography.displayMd),
      h1: heading(AppTypography.h1),
      h2: heading(AppTypography.h2),
      h3: heading(AppTypography.h3),
      h4: heading(AppTypography.h4, serifEligible: false),
      bodyLg: sized(AppTypography.bodyLg),
      body: sized(AppTypography.body),
      bodySm: sized(AppTypography.bodySm),
      labelLg: sized(AppTypography.labelLg),
      label: sized(AppTypography.label),
      labelSm: sized(AppTypography.labelSm),
      caption: sized(AppTypography.caption),
      // Monospace is a data face — hashes, byte counts, log lines. It follows
      // the size scale so it keeps rhythm with the body, but never the family.
      mono: sized(AppTypography.mono),
    );
  }

  final TextStyle displayLg;
  final TextStyle displayMd;
  final TextStyle h1;
  final TextStyle h2;
  final TextStyle h3;
  final TextStyle h4;
  final TextStyle bodyLg;
  final TextStyle body;
  final TextStyle bodySm;
  final TextStyle labelLg;
  final TextStyle label;
  final TextStyle labelSm;
  final TextStyle caption;
  final TextStyle mono;

  /// Every style, for the tests that assert the size floor preset-wide.
  List<TextStyle> get all => [
        displayLg,
        displayMd,
        h1,
        h2,
        h3,
        h4,
        bodyLg,
        body,
        bodySm,
        labelLg,
        label,
        labelSm,
        caption,
        mono,
      ];

  /// The Material [TextTheme], slot for slot as [AppTypography.textTheme]
  /// maps it, so Material's own widgets follow the preset too.
  TextTheme get textTheme => TextTheme(
        displayLarge: h1,
        displayMedium: h2,
        displaySmall: h3,
        headlineMedium: h4,
        bodyLarge: bodyLg,
        bodyMedium: body,
        bodySmall: bodySm,
        labelLarge: labelLg,
        labelMedium: label,
        labelSmall: labelSm,
      );

  static TextStyle _sized(TextStyle base, AppTypeScale scale) {
    final size = base.fontSize;
    final height = base.height;
    return base.copyWith(
      fontSize: size == null ? null : _stepSize(size * scale.sizeScale),
      height: height == null ? null : height * scale.lineHeightScale,
    );
  }

  static TextStyle _heading(
    TextStyle base,
    AppTypeScale scale, {
    required bool serifEligible,
  }) {
    var style = _sized(base, scale);
    if (scale.headingTracking != 0) {
      style = style.copyWith(
        letterSpacing: (base.letterSpacing ?? 0) + scale.headingTracking,
      );
    }
    final weight = scale.headingWeight;
    if (weight != null) {
      style = style.copyWith(
        fontWeight: weight,
        fontVariations: [FontVariation('wght', weight.value.toDouble())],
      );
    }
    switch (scale.headingFace) {
      case AppHeadingFace.display:
        return style;
      case AppHeadingFace.body:
        return style.copyWith(fontFamily: AppTypography.fontFamilyBody);
      case AppHeadingFace.serif:
        if (!serifEligible) return style;
        return style.copyWith(
          fontFamily: kPresetSerifStack.first,
          fontFamilyFallback: kPresetSerifStack.sublist(1),
        );
    }
  }

  /// Rounds to the nearest half-pixel and never goes below the legibility
  /// floor — a scale of 0.9 must not turn an 11px caption into a 9.9px one.
  static double _stepSize(double raw) =>
      math.max(kMinPresetFontSize, (raw * 2).roundToDouble() / 2);

  static AppTextStyles lerp(AppTextStyles a, AppTextStyles b, double t) {
    TextStyle l(TextStyle x, TextStyle y) => TextStyle.lerp(x, y, t)!;
    return AppTextStyles(
      displayLg: l(a.displayLg, b.displayLg),
      displayMd: l(a.displayMd, b.displayMd),
      h1: l(a.h1, b.h1),
      h2: l(a.h2, b.h2),
      h3: l(a.h3, b.h3),
      h4: l(a.h4, b.h4),
      bodyLg: l(a.bodyLg, b.bodyLg),
      body: l(a.body, b.body),
      bodySm: l(a.bodySm, b.bodySm),
      labelLg: l(a.labelLg, b.labelLg),
      label: l(a.label, b.label),
      labelSm: l(a.labelSm, b.labelSm),
      caption: l(a.caption, b.caption),
      mono: l(a.mono, b.mono),
    );
  }
}

// ── Layout defaults ──────────────────────────────────────────────────────────

/// How a browsable list of series presents itself before the reader overrides
/// it.
enum SeriesLayout {
  /// Poster grid — artwork first.
  grid,

  /// Rows — title and metadata first.
  list,
}

/// How much a series card says beside its cover.
enum CardDetail {
  /// Cover and title only.
  minimal,

  /// The shipped card: cover, title, and the chapter/progress line.
  standard,
}

@immutable
class AppLayoutDefaults {
  const AppLayoutDefaults({
    required this.seriesLayout,
    required this.gridColumnBias,
    required this.gridAspectRatio,
    required this.cardDetail,
  });

  /// The layout a browse/library surface uses when the reader has not chosen
  /// one. An explicit choice always wins — a preset sets defaults, it does not
  /// overrule a person.
  final SeriesLayout seriesLayout;

  /// Columns added to (or removed from) the viewport's natural column count.
  final int gridColumnBias;

  /// `childAspectRatio` for the poster grid — cover plus caption block.
  final double gridAspectRatio;

  final CardDetail cardDetail;

  /// The viewport's natural column count, biased by this preset and clamped to
  /// a range that still shows a readable cover.
  ///
  /// Every poster grid in the app routes through here so they stay in step —
  /// including the loading skeleton, which has to lay out the same number of
  /// columns as the grid it is standing in for or the page jumps when the data
  /// lands.
  int columnsFor(int base) => (base + gridColumnBias).clamp(2, 6);
}

// ── Motion ───────────────────────────────────────────────────────────────────

@immutable
class AppMotion {
  const AppMotion({
    required this.scale,
    required this.scrollReveal,
    required this.pressScale,
  });

  /// Multiplier on animation durations. Zero is not offered: an instant swap
  /// of a large surface reads as a glitch, and the accessibility answer to "no
  /// animation at all" is the platform's own reduce-motion flag, not a preset.
  final double scale;

  /// Whether list and grid items fade/slide in as they enter the viewport.
  final bool scrollReveal;

  /// Scale a tappable surface shrinks to while held. 1.0 disables the effect.
  final double pressScale;

  Duration scaled(Duration base) =>
      Duration(microseconds: (base.inMicroseconds * scale).round());

  static AppMotion lerp(AppMotion a, AppMotion b, double t) {
    final target = t < 0.5 ? a : b;
    double l(double x, double y) => x + (y - x) * t;
    return AppMotion(
      scale: l(a.scale, b.scale),
      scrollReveal: target.scrollReveal,
      pressScale: l(a.pressScale, b.pressScale),
    );
  }
}

// ── Reader chrome ────────────────────────────────────────────────────────────

/// How much furniture the reader shows, and for how long.
@immutable
class AppReaderChrome {
  const AppReaderChrome({
    required this.autoHideAfter,
    required this.surfaceOpacity,
  });

  /// Idle time before the reader's top and bottom bars retire themselves.
  final Duration autoHideAfter;

  /// Alpha of those bars. Lower than [AppSurfaceStyle.chromeOpacity] on every
  /// preset: the reader's furniture sits directly on the page being read and
  /// is meant to be "almost invisible" while still legible.
  final double surfaceOpacity;
}
