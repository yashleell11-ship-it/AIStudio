import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/features/downloads/models/queue_download_response.dart';

String queueDownloadFeedbackMessage(QueueDownloadResponse response) {
  final queued = response.queued.length;
  final skipped = response.skipped.length;
  final parts = <String>[];

  if (queued > 0) {
    parts.add('Queued $queued chapter${queued == 1 ? '' : 's'}');
  }
  if (skipped > 0) {
    parts.add('Skipped $skipped already downloaded');
  }
  if (parts.isEmpty) {
    return 'No chapters queued';
  }
  return parts.join('\n');
}

void showQueueDownloadSnackBar(
  BuildContext context,
  QueueDownloadResponse response,
) {
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(
      content: Text(queueDownloadFeedbackMessage(response)),
      action: SnackBarAction(
        label: 'Downloads',
        onPressed: () {
          ScaffoldMessenger.of(context).hideCurrentSnackBar();
          context.go(Routes.downloads);
        },
      ),
    ),
  );
}
