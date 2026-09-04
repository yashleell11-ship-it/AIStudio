import 'dart:math' as math;
import 'dart:ui';

/// WCAG 2.x relative luminance of [color] (0 = black, 1 = white).
///
/// https://www.w3.org/TR/WCAG21/#dfn-relative-luminance — each sRGB channel
/// is linearised, then weighted by the eye's sensitivity to it.
double relativeLuminance(Color color) {
  double linear(double channel) => channel <= 0.04045
      ? channel / 12.92
      : math.pow((channel + 0.055) / 1.055, 2.4).toDouble();
  return 0.2126 * linear(color.r) +
      0.7152 * linear(color.g) +
      0.0722 * linear(color.b);
}

/// WCAG contrast ratio between two colours, 1:1 … 21:1. Order-independent.
double contrastRatio(Color a, Color b) {
  final la = relativeLuminance(a);
  final lb = relativeLuminance(b);
  final lighter = math.max(la, lb);
  final darker = math.min(la, lb);
  return (lighter + 0.05) / (darker + 0.05);
}
