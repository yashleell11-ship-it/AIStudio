import 'package:flutter/painting.dart';
import 'package:manhwamaniacs/core/platform/native_bridge.dart';

/// Number of upcoming pages to warm ahead of the visible page. Generous:
/// prioritise smooth fast-scrolling over memory frugality.
const int readerPrefetchAhead = 8;

/// In-memory decoded-image budget floor while reading — the same fixed
/// value every device got before RAM-aware sizing existed, and never gone
/// below regardless of device memory (shrinking a cache "to save memory"
/// trades away smoothness, which this app always favours; see
/// [_computeCacheBudget]).
const int _readerImageCacheFloorBytes = 384 << 20; // 384 MB

/// Ceiling so a very high-RAM device doesn't over-allocate for no benefit.
const int _readerImageCacheCeilingBytes = 768 << 20; // 768 MB

/// Fraction of total device RAM the cache scales toward, between the floor
/// and ceiling above.
const double _readerImageCacheRamFraction = 0.08;

/// Target decode width (physical px) for a page displayed at [logicalWidth].
///
/// Decoding at the on-screen size — rather than the source's native resolution
/// — is the single biggest memory win for a webtoon reader: a tall strip that
/// would otherwise allocate a >100 MB bitmap is downsampled to the display
/// size. Returns ``null`` (no resize) when the width is unknown.
int? readerDecodeWidth(double? logicalWidth, double devicePixelRatio) {
  if (logicalWidth == null || logicalWidth <= 0) return null;
  final dpr = devicePixelRatio <= 0 ? 1.0 : devicePixelRatio;
  final px = (logicalWidth * dpr).round();
  // Cap generously — favour crisp, high-quality pages over saving memory,
  // while still guarding against a pathological viewport requesting an absurd
  // bitmap. Most sources are well under this, so it rarely downsamples.
  const maxDecodeWidth = 2880;
  return px.clamp(1, maxDecodeWidth);
}

/// Raise the global image cache budget for reading, scaled up on devices with
/// abundant RAM. Idempotent and only ever grows the budget, never shrinks a
/// larger one another surface may have set.
Future<void> tuneReaderImageCache(NativeBridge bridge) async {
  final cache = PaintingBinding.instance.imageCache;
  final targetBytes = await _computeCacheBudget(bridge);
  if (cache.maximumSizeBytes < targetBytes) {
    cache.maximumSizeBytes = targetBytes;
  }
}

/// [_readerImageCacheFloorBytes] on every device (never regresses below what
/// the app always shipped), scaling up toward [_readerImageCacheCeilingBytes]
/// on devices with enough total RAM to spare. Falls back to the floor
/// wherever device memory can't be read (non-Android, channel failure) —
/// exactly today's fixed behaviour.
Future<int> _computeCacheBudget(NativeBridge bridge) async {
  final info = await bridge.getDeviceMemoryInfo();
  if (info == null) return _readerImageCacheFloorBytes;
  final scaled = (info.totalBytes * _readerImageCacheRamFraction).round();
  return scaled.clamp(_readerImageCacheFloorBytes, _readerImageCacheCeilingBytes);
}
