import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:manhwamaniacs/core/logging/app_logger.dart';

/// Whether the reader reports how its pages actually decoded.
///
/// A `const` off [kDebugMode] rather than a runtime flag so the whole
/// diagnostic — the extra image resolve included — is dead code the compiler
/// drops from a release build.
const bool readerDecodeDiagnosticsEnabled = kDebugMode;

/// Texture-axis sizes a mobile GPU reports as `maxImageDimension2D`.
///
/// Impeller clamps each axis against this **independently** and then
/// CPU-rescales the decode into the clamped box
/// (`ImageDecoderImpeller::DecompressTexture` → `ResizeOnCpu`, traced as
/// `SlowCPUDecodeScale`). Aspect ratio is not preserved, so a webtoon strip
/// taller than the limit is not letterboxed or cropped — it is squashed, after
/// paying for a full-size decode and a second allocation to shrink it. A
/// decoded height landing exactly on one of these is the fingerprint.
const List<int> readerTextureAxisLimits = <int>[4096, 8192, 16384];

/// The height a page of [declaredWidth] x [declaredHeight] should decode to
/// when asked for [requestedWidth], or ``null`` when the source never declared
/// its dimensions.
///
/// `ResizeImage` never upscales, so a request wider than the source is a no-op
/// and the height comes out untouched.
int? readerExpectedDecodedHeight({
  required int? declaredWidth,
  required int? declaredHeight,
  required int? requestedWidth,
}) {
  if (declaredWidth == null || declaredHeight == null) return null;
  if (declaredWidth <= 0 || declaredHeight <= 0) return null;
  final target =
      requestedWidth == null ? declaredWidth : math.min(requestedWidth, declaredWidth);
  if (target <= 0) return null;
  return (declaredHeight * target / declaredWidth).round();
}

/// What is worth saying about a page that did not decode to the size it was
/// asked for, or ``null`` when it decoded exactly as expected.
///
/// Pure and separate from [reportReaderDecode] so the wording — the part the
/// owner actually has to act on — can be asserted in a test.
String? readerDecodeReport({
  required String label,
  required int? declaredWidth,
  required int? declaredHeight,
  required int? requestedWidth,
  required int decodedWidth,
  required int decodedHeight,
}) {
  if (decodedWidth <= 0 || decodedHeight <= 0) return null;

  final expectedHeight = readerExpectedDecodedHeight(
    declaredWidth: declaredWidth,
    declaredHeight: declaredHeight,
    requestedWidth: requestedWidth,
  );
  // One pixel of slack: the decoder rounds the scaled height and so do we.
  final mismatched =
      expectedHeight != null && (decodedHeight - expectedHeight).abs() > 1;
  final atLimit = readerTextureAxisLimits.contains(decodedHeight);
  if (!mismatched && !atLimit) return null;

  final asked = requestedWidth == null ? 'native width' : '${requestedWidth}px wide';
  final declared = (declaredWidth == null || declaredHeight == null)
      ? 'source size not declared'
      : 'source ${declaredWidth}x$declaredHeight';
  final buffer = StringBuffer(
    'reader/decode "$label": $declared, asked for $asked, '
    'got ${decodedWidth}x$decodedHeight',
  );

  if (atLimit) {
    buffer.write(
      ' — height is exactly $decodedHeight, a GPU max texture size. Impeller '
      'clamps texture axes independently, so this page is being displayed '
      'SQUASHED vertically and paid a full-size decode plus a CPU rescale '
      '(SlowCPUDecodeScale) to get there',
    );
    if (expectedHeight != null && expectedHeight > decodedHeight) {
      final squash = expectedHeight / decodedHeight;
      buffer.write(' — ${squash.toStringAsFixed(2)}x too short');
    } else if (expectedHeight == null) {
      buffer.write(', unless this page really is $decodedHeight px tall');
    }
    buffer.write('.');
  } else {
    buffer.write(
      ' — expected height $expectedHeight. Something resized this page before '
      'the decoder saw it.',
    );
  }
  return buffer.toString();
}

/// Log [readerDecodeReport], in debug builds only.
void reportReaderDecode({
  required String label,
  required int? declaredWidth,
  required int? declaredHeight,
  required int? requestedWidth,
  required int decodedWidth,
  required int decodedHeight,
}) {
  if (!readerDecodeDiagnosticsEnabled) return;
  final report = readerDecodeReport(
    label: label,
    declaredWidth: declaredWidth,
    declaredHeight: declaredHeight,
    requestedWidth: requestedWidth,
    decodedWidth: decodedWidth,
    decodedHeight: decodedHeight,
  );
  if (report != null) appLogger.w(report);
}
