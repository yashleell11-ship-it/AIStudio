import 'package:flutter/foundation.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// A point-in-time snapshot of rendering performance, derived from Flutter's
/// [FrameTiming] stream. All durations are in milliseconds.
class PerformanceSnapshot {
  const PerformanceSnapshot({
    this.fps = 0,
    this.avgFrameMs = 0,
    this.worstFrameMs = 0,
    this.avgBuildMs = 0,
    this.avgRasterMs = 0,
    this.jankPercent = 0,
    this.sampleCount = 0,
  });

  /// Frames per second measured over the recent sampling window.
  final double fps;

  /// Average total frame time (build + raster) over the window.
  final double avgFrameMs;

  /// Slowest single frame observed in the window — the spike users feel.
  final double worstFrameMs;

  /// Average UI-thread (build/layout/paint) time — the "CPU" cost of a frame.
  final double avgBuildMs;

  /// Average raster-thread time — the "GPU" cost of a frame.
  final double avgRasterMs;

  /// Percentage of frames in the window that missed the target budget.
  final double jankPercent;

  /// How many frames contributed to this snapshot.
  final int sampleCount;

  bool get hasData => sampleCount > 0;
}

/// Collects [FrameTiming] samples and exposes rolling performance metrics.
///
/// Registered against [SchedulerBinding.addTimingsCallback]. The callback is
/// cheap (it only appends to a bounded ring buffer); metric aggregation and
/// listener notification are throttled to [_notifyIntervalMs] so the monitor
/// never becomes a source of jank itself. Injected via
/// [performanceMonitorProvider] so it can be faked in tests.
class PerformanceMonitor extends ChangeNotifier {
  PerformanceMonitor();

  static const int _windowSize = 120;
  static const int _notifyIntervalMs = 500;

  final List<FrameTiming> _window = <FrameTiming>[];
  bool _running = false;
  int _lastNotifyMs = 0;

  /// Frame budget in milliseconds, derived from the display refresh rate.
  /// A frame slower than this counts toward the jank percentage.
  double _frameBudgetMs = 1000.0 / 60.0;

  PerformanceSnapshot _snapshot = const PerformanceSnapshot();
  PerformanceSnapshot get snapshot => _snapshot;

  bool get isRunning => _running;

  /// Update the jank budget to match the currently active refresh rate.
  void setTargetRefreshRate(double hz) {
    if (hz <= 0) return;
    _frameBudgetMs = 1000.0 / hz;
  }

  void start() {
    if (_running) return;
    _running = true;
    _window.clear();
    SchedulerBinding.instance.addTimingsCallback(_onTimings);
  }

  void stop() {
    if (!_running) return;
    _running = false;
    SchedulerBinding.instance.removeTimingsCallback(_onTimings);
  }

  void _onTimings(List<FrameTiming> timings) {
    _window.addAll(timings);
    if (_window.length > _windowSize) {
      _window.removeRange(0, _window.length - _windowSize);
    }

    final nowMs = DateTime.now().millisecondsSinceEpoch;
    if (nowMs - _lastNotifyMs < _notifyIntervalMs) return;
    _lastNotifyMs = nowMs;
    _recompute();
    notifyListeners();
  }

  void _recompute() {
    if (_window.isEmpty) {
      _snapshot = const PerformanceSnapshot();
      return;
    }

    var totalFrameUs = 0.0;
    var totalBuildUs = 0.0;
    var totalRasterUs = 0.0;
    var worstUs = 0.0;
    var jankCount = 0;
    final budgetUs = _frameBudgetMs * 1000.0;

    for (final t in _window) {
      final buildUs = t.buildDuration.inMicroseconds.toDouble();
      final rasterUs = t.rasterDuration.inMicroseconds.toDouble();
      final frameUs = buildUs + rasterUs;
      totalBuildUs += buildUs;
      totalRasterUs += rasterUs;
      totalFrameUs += frameUs;
      if (frameUs > worstUs) worstUs = frameUs;
      if (frameUs > budgetUs) jankCount++;
    }

    final count = _window.length;
    final avgFrameMs = (totalFrameUs / count) / 1000.0;
    final fps = avgFrameMs > 0 ? (1000.0 / avgFrameMs).clamp(0, 1000) : 0.0;

    _snapshot = PerformanceSnapshot(
      fps: fps.toDouble(),
      avgFrameMs: avgFrameMs,
      worstFrameMs: worstUs / 1000.0,
      avgBuildMs: (totalBuildUs / count) / 1000.0,
      avgRasterMs: (totalRasterUs / count) / 1000.0,
      jankPercent: (jankCount / count) * 100.0,
      sampleCount: count,
    );
  }

  @override
  void dispose() {
    stop();
    super.dispose();
  }
}

/// Process-wide performance monitor. A single instance so diagnostics reflect
/// real app rendering; callers `start()`/`stop()` around the screen lifecycle.
final performanceMonitorProvider = Provider<PerformanceMonitor>(
  (ref) {
    final monitor = PerformanceMonitor();
    ref.onDispose(monitor.dispose);
    return monitor;
  },
  name: 'performanceMonitor',
);
