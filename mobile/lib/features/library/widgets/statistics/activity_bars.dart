import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';

/// A bar chart drawn by hand.
///
/// Deliberately a [CustomPainter] and not a charting package: this app's iOS
/// build runs off a CI-generated `Podfile.lock`, and a dependency that pulls a
/// new CocoaPod would put the pipeline that ships to the owner's phone at risk
/// — for a few dozen rounded rectangles.
///
/// Two things here are about *sparse* data, which is what a profile with a
/// handful of sessions actually has. Zero buckets still draw a faint floor tick
/// so the axis reads as a continuous timeline instead of a void with two spikes
/// in it, and the bars are laid out over the full width whatever the count, so
/// 24 hours and 30 days share one visual language.
class ActivityBars extends StatelessWidget {
  const ActivityBars({
    super.key,
    required this.values,
    required this.height,
    this.selectedIndex,
    this.onSelect,
    this.semanticsLabel,
  });

  /// One non-negative value per bucket, oldest/lowest first.
  final List<int> values;

  final double height;

  /// Highlighted bucket, or null for none.
  final int? selectedIndex;

  /// Called with the tapped bucket, or null when the same bucket is tapped
  /// again — tapping the selection off is how the readout gets back to its
  /// summary line without a second control.
  final ValueChanged<int?>? onSelect;

  final String? semanticsLabel;

  @override
  Widget build(BuildContext context) {
    final maxValue = values.fold<int>(0, math.max);

    Widget chart = LayoutBuilder(
      builder: (context, constraints) {
        final painter = CustomPaint(
          size: Size(constraints.maxWidth, height),
          painter: _ActivityBarsPainter(
            values: values,
            maxValue: maxValue,
            selectedIndex: selectedIndex,
            // Painters have no BuildContext, so the palette is captured here —
            // this build depends on Theme, so a switch repaints the chart.
            palette: context.colors,
          ),
        );
        if (onSelect == null || values.isEmpty) return painter;
        return GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTapDown: (details) {
            final slot = constraints.maxWidth / values.length;
            if (slot <= 0) return;
            final index = (details.localPosition.dx / slot)
                .floor()
                .clamp(0, values.length - 1);
            onSelect!(index == selectedIndex ? null : index);
          },
          child: painter,
        );
      },
    );

    if (semanticsLabel != null) {
      chart = Semantics(label: semanticsLabel, child: chart);
    }
    return SizedBox(height: height, child: chart);
  }
}

class _ActivityBarsPainter extends CustomPainter {
  _ActivityBarsPainter({
    required this.values,
    required this.maxValue,
    required this.selectedIndex,
    required this.palette,
  });

  final List<int> values;
  final int maxValue;
  final int? selectedIndex;
  final AppPalette palette;

  /// Height of a zero bucket's tick — enough to read as a mark on the axis,
  /// small enough that it can never be mistaken for a day with reading in it.
  static const double _floor = 2;

  /// Gap between two bars, and the cap on how fat one bar may get: without the
  /// cap a two-day range would draw two slabs the width of the card.
  static const double _gap = 3;
  static const double _maxBarWidth = 16;

  @override
  void paint(Canvas canvas, Size size) {
    if (values.isEmpty || size.width <= 0 || size.height <= 0) return;

    final baselineY = size.height;
    final slot = size.width / values.length;
    final barWidth = math.min(math.max(slot - _gap, 1.5), _maxBarWidth);
    final radius = Radius.circular(barWidth / 2);

    // One shader for the whole plot rather than one per bar, so a tall bar is
    // brighter at its tip than a short bar is at its own — the gradient reads
    // as depth in the chart instead of as a per-bar decoration.
    final barPaint = Paint()
      ..shader = LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [palette.amber400, palette.accent],
      ).createShader(Rect.fromLTWH(0, 0, size.width, size.height));
    final emptyPaint = Paint()..color = palette.fg.withAlpha(28);
    final selectedPaint = Paint()..color = palette.fg;

    final baselinePaint = Paint()
      ..color = palette.border
      ..strokeWidth = 1;
    canvas.drawLine(
      Offset(0, baselineY - 0.5),
      Offset(size.width, baselineY - 0.5),
      baselinePaint,
    );

    for (var i = 0; i < values.length; i++) {
      final value = values[i];
      final fraction = maxValue > 0 ? value / maxValue : 0.0;
      final barHeight = value <= 0
          ? _floor
          : math.max(_floor + 1, _floor + fraction * (size.height - _floor));
      final left = i * slot + (slot - barWidth) / 2;
      final rect = RRect.fromRectAndCorners(
        Rect.fromLTWH(left, baselineY - barHeight, barWidth, barHeight),
        topLeft: radius,
        topRight: radius,
      );
      canvas.drawRRect(
        rect,
        i == selectedIndex
            ? selectedPaint
            : (value > 0 ? barPaint : emptyPaint),
      );
    }
  }

  @override
  bool shouldRepaint(_ActivityBarsPainter old) =>
      old.selectedIndex != selectedIndex ||
      old.maxValue != maxValue ||
      old.palette != palette ||
      !_sameValues(old.values, values);

  static bool _sameValues(List<int> a, List<int> b) {
    if (identical(a, b)) return true;
    if (a.length != b.length) return false;
    for (var i = 0; i < a.length; i++) {
      if (a[i] != b[i]) return false;
    }
    return true;
  }
}
