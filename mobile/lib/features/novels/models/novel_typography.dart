/// Typography controls for the novel reader: size, leading, measure and face.
///
/// The ranges and defaults are the web's, value for value
/// (`frontend/src/features/novels/typography.ts`), so a book tuned on one
/// client reads the same on the other. What differs is how they are *spent*,
/// and only where the medium forces it — noted at each constant.
///
/// **System faces only.** The app bundles no webfont, so "serif" and "sans"
/// are families the phone already has. The stacks below lead with the best
/// long-form faces each platform ships and fall back through the usual
/// suspects, so the choice is a real change of face on both platforms rather
/// than "Georgia or nothing".
library;

enum NovelFontFamily {
  serif,
  sans;

  static NovelFontFamily fromWire(String? value) =>
      value == 'sans' ? NovelFontFamily.sans : NovelFontFamily.serif;

  String get wire => name;
}

/// Long-form serif stack.
///
/// Iowan Old Style (iOS, Apple Books' own face) and Charter are the two best
/// reading faces that ship on a device; Georgia is the near-universal floor.
/// Noto Serif is Android's own, and is listed before the generic because an
/// Android that resolves neither of the first three should still land on a
/// real book face rather than whatever `serif` maps to.
const List<String> kNovelSerifStack = <String>[
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

/// The platform UI face, which is what a sans reader actually wants here:
/// `null` family with these fallbacks resolves to SF on iOS and Roboto on
/// Android without naming either.
const List<String> kNovelSansStack = <String>[
  'SF Pro Text',
  'Roboto',
  'Helvetica Neue',
  'Noto Sans',
  'sans-serif',
];

List<String> novelFontStack(NovelFontFamily family) =>
    family == NovelFontFamily.sans ? kNovelSansStack : kNovelSerifStack;

/// Body size in logical pixels.
const double kMinNovelFontSize = 15;
const double kMaxNovelFontSize = 26;
const double kNovelFontSizeStep = 1;
const double kDefaultNovelFontSize = 19;

/// Unitless line-height multiplier. Generous by default — this is prose.
const double kMinNovelLineHeight = 1.4;
const double kMaxNovelLineHeight = 2.1;
const double kNovelLineHeightStep = 0.05;
const double kDefaultNovelLineHeight = 1.75;

/// Column width in characters.
const double kMinNovelMeasure = 48;
const double kMaxNovelMeasure = 88;
const double kNovelMeasureStep = 2;

/// The comfortable default: ~68 characters a line.
const double kDefaultNovelMeasure = 68;

/// Average character advance as a fraction of the font size, for turning a
/// measure in characters into a column width in logical pixels.
///
/// The web sets the column in `ch`, a unit the browser resolves against the
/// chosen face's own zero-width. Flutter has no such unit, so this is the
/// stand-in: 0.5em is the conventional figure for a mixed-case Latin serif at
/// text sizes, and the two faces on offer here sit either side of it.
///
/// A phone in portrait is narrower than even the minimum measure, so on that
/// screen this control does nothing at all and the column is simply the page.
/// It earns its place on a tablet and in landscape, where an un-capped column
/// runs to 120 characters and becomes genuinely hard to track back from.
const double kNovelMeasureEmFactor = 0.5;

/// The paragraph's first-line indent, in ems.
///
/// This is most of what makes prose read as a novel rather than a chat log:
/// paragraphs are INDENTED, not separated by blank lines. The first paragraph
/// of a chapter (and the one after a scene break) is set flush, as books set
/// them — an indent there marks a break from something that isn't there.
const double kNovelParagraphIndentEm = 1.4;

double _clampTo(double value, double min, double max, double fallback) {
  if (value.isNaN || value.isInfinite) return fallback;
  return value.clamp(min, max).toDouble();
}

double clampNovelFontSize(double value) => _clampTo(
      value,
      kMinNovelFontSize,
      kMaxNovelFontSize,
      kDefaultNovelFontSize,
    ).roundToDouble();

double clampNovelLineHeight(double value) {
  final clamped = _clampTo(
    value,
    kMinNovelLineHeight,
    kMaxNovelLineHeight,
    kDefaultNovelLineHeight,
  );
  // Two decimals: the step is 0.05 and repeated float arithmetic on it drifts.
  return (clamped * 100).round() / 100;
}

double clampNovelMeasure(double value) => _clampTo(
      value,
      kMinNovelMeasure,
      kMaxNovelMeasure,
      kDefaultNovelMeasure,
    ).roundToDouble();

/// Step a value and re-clamp — the +/- buttons in the type panel.
double stepNovelFontSize(double current, int steps) =>
    clampNovelFontSize(current + steps * kNovelFontSizeStep);

double stepNovelLineHeight(double current, int steps) =>
    clampNovelLineHeight(current + steps * kNovelLineHeightStep);

double stepNovelMeasure(double current, int steps) =>
    clampNovelMeasure(current + steps * kNovelMeasureStep);

/// The column width for [measure] characters at [fontSize], never wider than
/// the [available] width. Returning the available width (rather than
/// overflowing it) is what makes the control a cap rather than a demand.
double novelColumnWidth({
  required double measure,
  required double fontSize,
  required double available,
}) {
  final wanted = measure * fontSize * kNovelMeasureEmFactor;
  return wanted < available ? wanted : available;
}
