import 'package:flutter_riverpod/flutter_riverpod.dart';

const double minReaderZoom = 0.5;
const double maxReaderZoom = 3.0;
const double readerZoomStep = 0.1;

class ReaderUiState {
  const ReaderUiState({
    this.controlsVisible = true,
    this.zoomLevel = 1,
  });

  final bool controlsVisible;
  final double zoomLevel;

  ReaderUiState copyWith({
    bool? controlsVisible,
    double? zoomLevel,
  }) =>
      ReaderUiState(
        controlsVisible: controlsVisible ?? this.controlsVisible,
        zoomLevel: zoomLevel ?? this.zoomLevel,
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

  void zoomIn() =>
      state = state.copyWith(zoomLevel: _clampZoom(state.zoomLevel + readerZoomStep));

  void zoomOut() =>
      state = state.copyWith(zoomLevel: _clampZoom(state.zoomLevel - readerZoomStep));

  void resetZoom() => state = state.copyWith(zoomLevel: 1);
}

final readerUiProvider =
    NotifierProvider<ReaderUiController, ReaderUiState>(ReaderUiController.new);
