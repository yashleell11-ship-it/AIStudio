import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';

/// Fixture cover art, painted here rather than shipped as image files.
///
/// The install page is public, so nothing a real source serves may appear in
/// it — not a title, not a cover. Painting the art in-repo is the only way to
/// make that a property of the code rather than a promise: there is no image
/// on disk to go stale, and no way for a source's artwork to reach the page.
///
/// The look is the app's own — the Eclipse palette's inks, Syne for the title —
/// so the shelf reads as designed rather than as a wall of missing images, and
/// the plates are plainly abstract rather than pretending to be scans.
class ShotCoverArt {
  const ShotCoverArt({required this.title, required this.seed});

  final String title;
  final int seed;

  static const _inks = <List<Color>>[
    [Color(0xFF2A1E4A), Color(0xFF7C4A63)],
    [Color(0xFF10323C), Color(0xFF3E8B7F)],
    [Color(0xFF3A1F14), Color(0xFFC2703C)],
    [Color(0xFF1B2340), Color(0xFF4E6FA8)],
    [Color(0xFF32172B), Color(0xFF9C4A5E)],
    [Color(0xFF14301F), Color(0xFF6F9E52)],
    [Color(0xFF2D2410), Color(0xFFB59139)],
    [Color(0xFF201C3A), Color(0xFF6455A8)],
    [Color(0xFF0F2A33), Color(0xFF5D8FA8)],
  ];

  /// PNG bytes at [width]x[height] device pixels.
  ///
  /// Async because rasterising a `Picture` is; call it from
  /// `WidgetTester.runAsync`, never from a bare test body.
  Future<Uint8List> toPng({int width = 420, int height = 630}) async {
    final recorder = ui.PictureRecorder();
    final canvas = Canvas(recorder);
    final size = Size(width.toDouble(), height.toDouble());
    _paint(canvas, size);
    final image = await recorder.endRecording().toImage(width, height);
    final data = await image.toByteData(format: ui.ImageByteFormat.png);
    image.dispose();
    return data!.buffer.asUint8List();
  }

  void _paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    final random = math.Random(seed);
    final ink = _inks[seed % _inks.length];

    canvas.drawRect(
      rect,
      Paint()
        ..shader = LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: ink,
        ).createShader(rect),
    );

    // A soft light source, offset so no two plates sit the same way.
    final glowCentre = Offset(
      size.width * (0.25 + random.nextDouble() * 0.5),
      size.height * (0.18 + random.nextDouble() * 0.3),
    );
    canvas.drawCircle(
      glowCentre,
      size.width * 0.75,
      Paint()
        ..shader = RadialGradient(
          colors: [Colors.white.withValues(alpha: 0.22), Colors.transparent],
        ).createShader(
          Rect.fromCircle(center: glowCentre, radius: size.width * 0.75),
        ),
    );

    // Concentric arcs — a motif, not a picture of anything.
    final arcPaint = Paint()
      ..style = PaintingStyle.stroke
      ..color = Colors.white.withValues(alpha: 0.16);
    final arcCentre = Offset(
      size.width * (0.2 + random.nextDouble() * 0.6),
      size.height * (0.3 + random.nextDouble() * 0.25),
    );
    for (var i = 0; i < 4; i++) {
      arcPaint.strokeWidth = size.width * (0.004 + i * 0.002);
      canvas.drawCircle(
        arcCentre,
        size.width * (0.16 + i * 0.13),
        arcPaint,
      );
    }

    // A single diagonal band for weight.
    final band = Path()
      ..moveTo(0, size.height * (0.52 + random.nextDouble() * 0.12))
      ..lineTo(size.width, size.height * (0.34 + random.nextDouble() * 0.12))
      ..lineTo(size.width, size.height)
      ..lineTo(0, size.height)
      ..close();
    canvas.drawPath(
      band,
      Paint()..color = Colors.black.withValues(alpha: 0.32),
    );

    // Bottom scrim so the title always clears its background.
    canvas.drawRect(
      Rect.fromLTRB(0, size.height * 0.52, size.width, size.height),
      Paint()
        ..shader = LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Colors.transparent, Colors.black.withValues(alpha: 0.72)],
        ).createShader(
          Rect.fromLTRB(0, size.height * 0.52, size.width, size.height),
        ),
    );

    _paintTitle(canvas, size);
  }

  void _paintTitle(Canvas canvas, Size size) {
    final pad = size.width * 0.09;
    final builder = ui.ParagraphBuilder(
      ui.ParagraphStyle(
        fontFamily: 'Syne',
        fontSize: size.width * 0.115,
        fontWeight: FontWeight.w700,
        height: 1.14,
        maxLines: 3,
        ellipsis: '…',
      ),
    )
      ..pushStyle(
        ui.TextStyle(
          color: Colors.white,
          fontFamily: 'Syne',
          fontWeight: FontWeight.w700,
          fontVariations: const [FontVariation('wght', 700)],
          letterSpacing: -size.width * 0.002,
          shadows: [
            Shadow(
              color: Colors.black.withValues(alpha: 0.55),
              blurRadius: size.width * 0.05,
            ),
          ],
        ),
      )
      ..addText(title);
    final paragraph = builder.build()
      ..layout(ui.ParagraphConstraints(width: size.width - pad * 2));

    final baseline = size.height - pad - paragraph.height;
    canvas.drawParagraph(paragraph, Offset(pad, baseline));

    // A short accent rule above the title, the way the app rules its headings.
    canvas.drawRect(
      Rect.fromLTWH(
        pad,
        baseline - size.height * 0.035,
        size.width * 0.16,
        size.height * 0.006,
      ),
      Paint()..color = const Color(0xFFE8A33D),
    );
  }
}
