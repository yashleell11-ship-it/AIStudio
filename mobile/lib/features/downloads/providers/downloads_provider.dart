import 'dart:async';

import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/core/utils/result.dart';
import 'package:aistudio_mobile/features/downloads/models/download_item.dart';
import 'package:aistudio_mobile/features/downloads/models/download_metrics.dart';
import 'package:aistudio_mobile/features/downloads/utils/download_grouping.dart';
import 'package:aistudio_mobile/shared/providers/repository_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class DownloadsState {
  const DownloadsState({
    required this.items,
    required this.metrics,
    this.actionPending = false,
    this.feedbackMessage,
    this.actionError,
  });

  final List<DownloadItem> items;
  final DownloadMetrics metrics;
  final bool actionPending;
  final String? feedbackMessage;
  final AppError? actionError;

  DownloadsState copyWith({
    List<DownloadItem>? items,
    DownloadMetrics? metrics,
    bool? actionPending,
    String? feedbackMessage,
    AppError? actionError,
    bool clearFeedback = false,
    bool clearActionError = false,
  }) =>
      DownloadsState(
        items: items ?? this.items,
        metrics: metrics ?? this.metrics,
        actionPending: actionPending ?? this.actionPending,
        feedbackMessage:
            clearFeedback ? null : (feedbackMessage ?? this.feedbackMessage),
        actionError: clearActionError ? null : (actionError ?? this.actionError),
      );
}

final downloadFilterProvider = StateProvider<DownloadFilterTab>(
  (ref) => DownloadFilterTab.all,
  name: 'downloadFilter',
);

final downloadsProvider =
    AsyncNotifierProvider.autoDispose<DownloadsNotifier, DownloadsState>(
  DownloadsNotifier.new,
  name: 'downloads',
);

class DownloadsNotifier extends AutoDisposeAsyncNotifier<DownloadsState> {
  Timer? _pollTimer;

  @override
  Future<DownloadsState> build() async {
    ref.onDispose(() => _pollTimer?.cancel());
    final data = await _fetch();
    _schedulePolling(data.items);
    return data;
  }

  Future<void> refresh() async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(() async {
      final data = await _fetch();
      _schedulePolling(data.items);
      return data;
    });
  }

  Future<void> _silentRefresh() async {
    final current = state.valueOrNull;
    if (current == null || current.actionPending) return;

    try {
      final data = await _fetch();
      _schedulePolling(data.items);
      state = AsyncData(
        current.copyWith(
          items: data.items,
          metrics: data.metrics,
          clearActionError: true,
        ),
      );
    } catch (_) {}
  }

  void _schedulePolling(List<DownloadItem> items) {
    _pollTimer?.cancel();
    final hasActive = items.any((item) => item.isDownloading || item.isQueued);
    final interval = hasActive
        ? const Duration(seconds: 2)
        : const Duration(seconds: 5);
    _pollTimer = Timer.periodic(interval, (_) {
      unawaited(_silentRefresh());
    });
  }

  Future<DownloadsState> _fetch() async {
    final repo = ref.read(downloadsRepositoryProvider);
    final itemsResult = await repo.listDownloads();
    final metricsResult = await repo.getMetrics();
    if (itemsResult.isErr) throw itemsResult.error;
    if (metricsResult.isErr) throw metricsResult.error;
    return DownloadsState(
      items: itemsResult.value,
      metrics: metricsResult.value,
    );
  }

  Future<void> _runAction(
    Future<void> Function() action, {
    String? successMessage,
  }) async {
    final current = state.valueOrNull;
    if (current == null) return;

    state = AsyncData(
      current.copyWith(actionPending: true, clearFeedback: true, clearActionError: true),
    );

    try {
      await action();
      final refreshed = await _fetch();
      _schedulePolling(refreshed.items);
      state = AsyncData(
        refreshed.copyWith(
          actionPending: false,
          feedbackMessage: successMessage,
        ),
      );
    } catch (error) {
      final appError = error is AppError
          ? error
          : UnknownError(message: error.toString(), cause: error);
      state = AsyncData(
        current.copyWith(
          actionPending: false,
          actionError: appError,
        ),
      );
    }
  }

  Future<void> _runBulk(
    Future<Result<int>> Function() action,
    String label,
  ) async {
    final current = state.valueOrNull;
    if (current == null) return;

    state = AsyncData(
      current.copyWith(actionPending: true, clearFeedback: true, clearActionError: true),
    );

    final result = await action();
    if (result.isErr) {
      state = AsyncData(
        current.copyWith(actionPending: false, actionError: result.error),
      );
      return;
    }

    final refreshed = await _fetch();
    _schedulePolling(refreshed.items);
    final affected = result.value;
    state = AsyncData(
      refreshed.copyWith(
        actionPending: false,
        feedbackMessage:
            '$label: $affected chapter${affected == 1 ? '' : 's'} affected.',
      ),
    );
  }

  Future<void> pauseItem(int id) => _runAction(() async {
        final result = await ref.read(downloadsRepositoryProvider).pauseDownload(id);
        if (result.isErr) throw result.error;
      });

  Future<void> resumeItem(int id) => _runAction(() async {
        final result = await ref.read(downloadsRepositoryProvider).resumeDownload(id);
        if (result.isErr) throw result.error;
      });

  Future<void> cancelItem(int id) => _runAction(() async {
        final result = await ref.read(downloadsRepositoryProvider).cancelDownload(id);
        if (result.isErr) throw result.error;
      });

  Future<void> retryItem(int id) => _runAction(() async {
        final result = await ref.read(downloadsRepositoryProvider).retryDownload(id);
        if (result.isErr) throw result.error;
      });

  Future<void> pauseSeries(String sourceId, String seriesId) => _runBulk(
        () => ref.read(downloadsRepositoryProvider).pauseSeries(
              sourceId: sourceId,
              seriesId: seriesId,
            ),
        'Pause series',
      );

  Future<void> resumeSeries(String sourceId, String seriesId) => _runBulk(
        () => ref.read(downloadsRepositoryProvider).resumeSeries(
              sourceId: sourceId,
              seriesId: seriesId,
            ),
        'Resume series',
      );

  Future<void> cancelSeries(String sourceId, String seriesId) => _runBulk(
        () => ref.read(downloadsRepositoryProvider).cancelSeries(
              sourceId: sourceId,
              seriesId: seriesId,
            ),
        'Cancel series',
      );

  Future<void> pauseAll() => _runBulk(
        () => ref.read(downloadsRepositoryProvider).pauseAll(),
        'Pause all',
      );

  Future<void> resumeAll() => _runBulk(
        () => ref.read(downloadsRepositoryProvider).resumeAll(),
        'Resume all',
      );

  Future<void> cancelAll() => _runBulk(
        () => ref.read(downloadsRepositoryProvider).cancelAll(),
        'Cancel all',
      );
}
