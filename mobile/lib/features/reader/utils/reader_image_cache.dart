import 'dart:math' as math;

import 'package:flutter/painting.dart';
import 'package:manhwamaniacs/core/platform/native_bridge.dart';

/// Decoded-bitmap budget for the window of pages warmed from the visible one
/// forward.
///
/// This used to be a page count of 8, and a count is the wrong unit on this
/// corpus: a measured sweep of 487 pages across 44 live sources puts one
/// decoded page at 3 MB on mangadex and 44 MB on elftoon, so the same eight
/// pages are either an idle cache or ~400 MB of live bitmaps against a
/// [_readerImageCacheFloorBytes] budget that cannot hold them — at which point
/// the cache stops being a cache: every page turn evicts and every scroll back
/// re-decodes. Bytes are the unit that actually bounds the working set.
const int readerPrefetchBudgetBytes = 64 << 20; // 64 MB

/// Never warm fewer than this many pages, budget or no budget.
///
/// Two, not one: one means warming only the page already on screen, and the
/// heaviest sources — the ones the budget bites on — are exactly the ones
/// where waiting on a decode at every page turn would hurt most. Two always
/// leaves one page ahead in hand.
const int readerPrefetchMinPages = 2;

/// Never warm more than this many pages, budget or no budget. Past here the
/// limit stops being memory and starts being the number of image requests in
/// flight at once.
const int readerPrefetchMaxPages = 16;

/// What to charge a page whose size nothing knows yet.
///
/// Roughly the corpus' 75th percentile decoded page at a phone's decode width,
/// so it is pessimistic without being absurd. It only applies in the opening
/// frames of a chapter, before the first page has decoded: too small and a
/// heavy source over-warms once, unrecoverably, because the prefetch
/// high-water mark only moves forward; too large and a cheap source opens a
/// page or two shallow and corrects on the very next scroll event.
const int readerAssumedPageBytes = 24 << 20; // 24 MB

/// In-memory decoded-image budget floor while reading — the same fixed
/// value every device got before RAM-aware sizing existed, and never gone
/// below regardless of device memory (shrinking a cache "to save memory"
/// trades away smoothness, which this app always favours; see
/// [_computeCacheBudget]).
///
/// Deliberately unchanged now that [readerPrefetchBudgetBytes] bounds the
/// working set. The two are not the same budget: the prefetch budget caps what
/// is live *ahead* of the reader, this one decides how far *back* they can
/// scroll for free. Before, the live set alone could exceed this floor, so it
/// held nothing and every page was decoded twice; at ~90 MB live it holds
/// several screens of already-read pages, which is precisely the case it
/// exists for. Lowering it would hand back the scroll-back re-decodes; raising
/// it would buy nothing, because the prefetch no longer produces bitmaps fast
/// enough to fill it.
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

/// Bytes one page's decoded RGBA bitmap occupies, or ``null`` while its size
/// is not known well enough to say.
///
/// [pixelWidth] is the widest the bitmap can be — a source's declared width,
/// or the width a page actually decoded at — and [ratio] its width/height.
/// `ResizeImage` never upscales, so the decode lands at the narrower of that
/// and [decodeWidth] and the height follows from the ratio. Nothing here
/// changes what is decoded; it only prices it.
int? readerDecodedPageBytes({
  required int? decodeWidth,
  required int? pixelWidth,
  required double? ratio,
}) {
  if (pixelWidth == null || pixelWidth <= 0) return null;
  if (ratio == null || !ratio.isFinite || ratio <= 0) return null;
  final width =
      decodeWidth == null ? pixelWidth : math.min(decodeWidth, pixelWidth);
  if (width <= 0) return null;
  final height = (width / ratio).round();
  if (height <= 0) return null;
  return width * height * 4;
}

/// Index one past the last page worth warming, walking forward from
/// [fromIndex] until [budgetBytes] of decoded bitmap is spoken for.
///
/// [knownPageBytes] prices a page whose size is known and returns ``null`` for
/// one nothing has measured yet. An unknown page is charged whatever the last
/// known page cost — a chapter's pages come from one source, published at one
/// width and similar heights, so its neighbour predicts it far better than any
/// constant can — and [assumedPageBytes] only stands in before the first page
/// of a chapter has decoded.
///
/// The result is a page count again at the call site, which is the point: the
/// budget is what makes that count 1 on a 44 MB-per-page source and 15 on a
/// 3 MB one, instead of 8 on both.
int readerPrefetchTarget({
  required int fromIndex,
  required int pageCount,
  required int? Function(int index) knownPageBytes,
  int budgetBytes = readerPrefetchBudgetBytes,
  int assumedPageBytes = readerAssumedPageBytes,
  int minPages = readerPrefetchMinPages,
  int maxPages = readerPrefetchMaxPages,
}) {
  if (pageCount <= 0) return 0;
  final start = fromIndex.clamp(0, pageCount - 1);
  final limit = math.min(pageCount, start + math.max(1, maxPages));
  var assumed = assumedPageBytes;
  var spent = 0;
  var index = start;
  while (index < limit) {
    // Checked before the page is priced, so the budget is what has already
    // been committed — a single page heavier than the whole budget still gets
    // warmed rather than leaving the reader with nothing.
    if (index - start >= minPages && spent >= budgetBytes) break;
    final known = knownPageBytes(index);
    if (known != null && known > 0) assumed = known;
    spent += known ?? assumed;
    index++;
  }
  return index;
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
