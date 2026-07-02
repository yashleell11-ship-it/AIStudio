import 'package:aistudio_mobile/app/theme/app_spacing.dart';
import 'package:aistudio_mobile/app/theme/app_typography.dart';
import 'package:aistudio_mobile/features/downloads/utils/source_chapter_download_status.dart';
import 'package:flutter/material.dart';

class SourceChapterDownloadStatusBadge extends StatelessWidget {
  const SourceChapterDownloadStatusBadge({
    super.key,
    required this.status,
  });

  final SourceChapterDownloadUiStatus status;

  @override
  Widget build(BuildContext context) {
    if (status == SourceChapterDownloadUiStatus.none) {
      return const SizedBox.shrink();
    }

    final color = sourceChapterDownloadStatusColor(status);
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.xs),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: color.withAlpha(38),
          borderRadius: BorderRadius.circular(AppRadius.full),
          border: Border.all(color: color.withAlpha(102)),
        ),
        child: Text(
          sourceChapterDownloadStatusLabel(status),
          style: AppTypography.caption.copyWith(color: color),
        ),
      ),
    );
  }
}
