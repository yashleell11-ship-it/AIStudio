import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:manhwamaniacs/features/ocr/models/page_text.dart';

/// Runs text recognition on page images already on disk (spec §4).
///
/// Deliberately narrow: it takes **file paths**, never bytes. The only images
/// this app OCRs are pages the on-device store already downloaded, so handing
/// the native side a path lets Vision/ML Kit decode straight from disk
/// instead of ferrying multi-megabyte byte arrays across the method channel
/// once per page.
abstract interface class OcrEngine {
  /// Whether a native handler is actually registered and usable on this
  /// device. Every OCR affordance in the UI is gated on this: spec §4's
  /// "absent/failed platform impl → feature hidden" is the whole reason this
  /// exists as a separate call rather than letting the first `recognize`
  /// discover it.
  Future<bool> isAvailable();

  /// Recognizes each path in order, returning one [PageText] per input at
  /// the same index. [startPage] stamps the first result's page number and
  /// each subsequent result increments from there.
  ///
  /// Throws on a channel failure — callers decide whether one unreadable
  /// page should abort a chapter (it should not; see [OcrRunController]).
  Future<List<PageText>> recognize(List<String> imagePaths, {int startPage = 1});

  /// A short, stable identifier for whatever did the recognizing, uploaded
  /// as `engine` so a later re-OCR by a better engine is distinguishable
  /// from the one it replaced.
  Future<String> engineId();
}

/// The `mm/ocr` [MethodChannel] implementation — iOS Vision
/// (`ios/Runner/AppDelegate.swift`) and Android ML Kit
/// (`android/.../OcrChannel.kt`).
///
/// No plugin package sits behind this on either platform: iOS uses Vision, a
/// system framework compiled into the Runner target (Podfile.lock untouched,
/// which is load-bearing for the sideload pipeline), and Android uses an ML
/// Kit Gradle dependency wired by hand. Everywhere else — desktop, web, and
/// the `flutter test` host — [isAvailable] is false before a channel is ever
/// touched, so no test needs a mock handler to avoid a hang.
class MethodChannelOcrEngine implements OcrEngine {
  const MethodChannelOcrEngine();

  static const MethodChannel channel = MethodChannel('mm/ocr');

  /// Only the two platforms with a handler. Checked before every call so a
  /// desktop debug run or a widget test never blocks on a channel with
  /// nothing on the far end.
  static bool get _platformSupported =>
      !kIsWeb && (Platform.isIOS || Platform.isAndroid);

  @override
  Future<bool> isAvailable() async {
    if (!_platformSupported) return false;
    try {
      return await channel.invokeMethod<bool>('isAvailable') ?? false;
    } catch (_) {
      // MissingPluginException (handler never registered), or a native
      // throw on a device whose OCR framework is unavailable. Either way the
      // feature hides itself rather than offering a button that fails.
      return false;
    }
  }

  @override
  Future<String> engineId() async {
    if (!_platformSupported) return 'unavailable';
    try {
      final id = await channel.invokeMethod<String>('engineId');
      return (id == null || id.isEmpty) ? 'unknown' : id;
    } catch (_) {
      return 'unknown';
    }
  }

  @override
  Future<List<PageText>> recognize(
    List<String> imagePaths, {
    int startPage = 1,
  }) async {
    if (imagePaths.isEmpty) return const [];
    if (!_platformSupported) {
      throw StateError('OCR is not supported on this platform.');
    }

    final results = await channel.invokeMethod<List<Object?>>(
      'recognize',
      {'paths': imagePaths},
    );
    if (results == null) {
      throw StateError('OCR returned no result.');
    }

    return [
      for (var i = 0; i < results.length; i++)
        if (results[i] case final Map<Object?, Object?> raw)
          PageText.fromChannel(raw, page: startPage + i)
        else
          // A native handler that skipped a page (unreadable file, decode
          // failure) still has to keep the list aligned with the input, so
          // an unusable entry becomes empty text rather than shifting every
          // subsequent page number by one.
          PageText(page: startPage + i, text: ''),
    ];
  }
}
