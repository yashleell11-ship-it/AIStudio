import 'package:flutter_riverpod/flutter_riverpod.dart';

const double minReaderZoom = 0.5;
const double maxReaderZoom = 3.0;
const double readerZoomStep = 0.1;

/// Zoom level applied by a double-tap when currently at 1×.
const double doubleTapZoomLevel = 2.0;

/// Auto-scroll speed in pixels per second.
/// Slow ≈ 30, Medium ≈ 60, Fast ≈ 120.
const double readerAutoScrollSlow = 30.0;
const double readerAutoScrollMedium = 60.0;
const double readerAutoScrollFast = 120.0;

class ReaderUiState {
  const ReaderUiState({
    this.controlsVisible = true,
    this.zoomLevel = 1,
    this.isLocked = false,
    this.autoScrollEnabled = false,
    this.autoScrollSpeed = readerAutoScrollMedium,
  });

  final bool controlsVisible;
  final double zoomLevel;
  final bool isLocked;
  final bool autoScrollEnabled;

  /// Speed in pixels per second.
  final double autoScrollSpeed;

  ReaderUiState copyWith({
    bool? controlsVisible,
    double? zoomLevel,
    bool? isLocked,
    bool? autoScrollEnabled,
    double? autoScrollSpeed,
  }) =>
      ReaderUiState(
        controlsVisible: controlsVisible ?? this.controlsVisible,
        zoomLevel: zoomLevel ?? this.zoomLevel,
        isLocked: isLocked ?? this.isLocked,
        autoScrollEnabled: autoScrollEnabled ?? this.autoScrollEnabled,
        autoScrollSpeed: autoScrollSpeed ?? this.autoScrollSpeed,
      );
}

double _clampZoom(double zoom) =>
    double.parse(zoom.clamp(minReaderZoom, maxReaderZoom).toStringAsFixed(2));

class ReaderUiController extends Notifier<ReaderUiState> {
  @override
  ReaderUiState build() => const ReaderUiState();

  void toggleControls() =>
      state = state.copyWith(controlsVisible: !state.controlsVisible);

  void setControlsVisible(bool visible) =>
      state = state.copyWith(controlsVisible: visible);

  void setLocked(bool locked) =>
      state = state.copyWith(isLocked: locked);

  void zoomIn() =>
      state = state.copyWith(zoomLevel: _clampZoom(state.zoomLevel + readerZoomStep));

  void zoomOut() =>
      state = state.copyWith(zoomLevel: _clampZoom(state.zoomLevel - readerZoomStep));

  void resetZoom() => state = state.copyWith(zoomLevel: 1);

  /// Toggle between 1× and [doubleTapZoomLevel] for double-tap-to-zoom.
  void toggleDoubleTapZoom() => state = state.copyWith(
        zoomLevel: state.zoomLevel > 1.01 ? 1.0 : doubleTapZoomLevel,
      );

  void toggleAutoScroll() =>
      state = state.copyWith(autoScrollEnabled: !state.autoScrollEnabled);

  void stopAutoScroll() =>
      state = state.copyWith(autoScrollEnabled: false);

  void setAutoScrollSpeed(double speed) =>
      state = state.copyWith(autoScrollSpeed: speed);
}

final readerUiProvider =
    NotifierProvider<ReaderUiController, ReaderUiState>(ReaderUiController.new);
