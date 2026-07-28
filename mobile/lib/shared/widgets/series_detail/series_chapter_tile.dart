import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/features/downloads/utils/source_chapter_download_status.dart';
import 'package:manhwamaniacs/features/sources/utils/chapter_label.dart';
import 'package:manhwamaniacs/features/sources/widgets/source_chapter_download_status_badge.dart';
import 'package:manhwamaniacs/shared/widgets/glass_card.dart';

/// Multi-select state for one chapter row. Null on a list that cannot be
/// selected from (a library series with no source to download the rest from),
/// which is why this is a separate object rather than a nullable callback plus
/// a bool that would have to agree with it.
class SeriesChapterSelection {
  const SeriesChapterSelection({
    required this.selected,
    required this.onChanged,
    this.checkboxKey,
  });

  final bool selected;

  /// Null disables the checkbox without hiding it — used while a queue request
  /// is in flight, so the row does not jump as buttons appear and disappear.
  final ValueChanged<bool?>? onChanged;

  final Key? checkboxKey;
}

/// Trailing download control for one chapter row.
class SeriesChapterDownloadAction {
  const SeriesChapterDownloadAction({
    this.onPressed,
    this.retryable = false,
    this.buttonKey,
  });

  /// Null renders the button disabled — the honest state for a chapter that is
  /// already downloaded, already queued, or whose series is mid-request.
  final VoidCallback? onPressed;

  /// A previous attempt failed, so the affordance is "retry", not "download".
  final bool retryable;

  final Key? buttonKey;
}

/// One chapter row, identical on the library and source series pages.
///
/// Every distinction the two pages used to draw differently — read state,
/// download state, the chapter currently being read — is a flag here, so the
/// pages can differ in what they know about a chapter but never in how that
/// knowledge looks.
class SeriesChapterTile extends StatelessWidget {
  const SeriesChapterTile({
    super.key,
    required this.label,
    this.progressText,
    this.inProgress = false,
    this.downloadStatus = SourceChapterDownloadUiStatus.none,
    this.statusBadgeKey,
    this.isRead = false,
    this.isCurrent = false,
    this.onTap,
    this.selection,
    this.download,
  });

  final ChapterLabel label;

  /// "7/20 pages" — see `seriesChapterProgressText`.
  final String? progressText;

  /// Whether [progressText] describes a part-read chapter, which glows warm
  /// rather than staying muted like an untouched or finished one.
  final bool inProgress;

  final SourceChapterDownloadUiStatus downloadStatus;
  final Key? statusBadgeKey;

  /// Finished. Recedes the whole row so unread chapters stand out.
  final bool isRead;

  /// The chapter the reader would resume — carries the "Reading" pill.
  final bool isCurrent;

  final VoidCallback? onTap;
  final SeriesChapterSelection? selection;
  final SeriesChapterDownloadAction? download;

  @override
  Widget build(BuildContext context) {
    final selection = this.selection;
    final download = this.download;

    final card = Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: GlassCard(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (selection != null)
              Checkbox(
                key: selection.checkboxKey,
                value: selection.selected,
                onChanged: selection.onChanged,
              ),
            Expanded(
              child: InkWell(
                onTap: onTap,
                child: Padding(
                  padding: EdgeInsets.symmetric(
                    vertical: AppSpacing.sm,
                    // Rows without a checkbox would otherwise start hard against
                    // the card edge where selectable rows start inset.
                    horizontal: selection == null ? AppSpacing.md : 0,
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Flexible(
                            child: Text(
                              label.primary,
                              style: AppTypography.labelLg.copyWith(
                                color: isRead ? AppColors.muted : null,
                              ),
                            ),
                          ),
                          if (isCurrent) ...[
                            const SizedBox(width: AppSpacing.sm),
                            const _ReadingPill(),
                          ],
                        ],
                      ),
                      if (label.secondary != null)
                        Text(label.secondary!, style: AppTypography.bodySm),
                      if (progressText != null)
                        Text(
                          progressText!,
                          style: AppTypography.caption.copyWith(
                            color:
                                inProgress ? AppColors.primary : AppColors.muted,
                          ),
                        ),
                      SourceChapterDownloadStatusBadge(
                        key: statusBadgeKey,
                        status: downloadStatus,
                      ),
                    ],
                  ),
                ),
              ),
            ),
            if (download != null)
              IconButton(
                key: download.buttonKey,
                tooltip:
                    download.retryable ? 'Retry Download' : 'Download Chapter',
                onPressed: download.onPressed,
                icon: Icon(
                  download.retryable ? Icons.refresh : Icons.download_outlined,
                ),
              ),
          ],
        ),
      ),
    );

    // Read chapters recede: dropping the whole card's opacity over the dark
    // background reads as a darker, muted "already read" row.
    return isRead ? Opacity(opacity: 0.6, child: card) : card;
  }
}

class _ReadingPill extends StatelessWidget {
  const _ReadingPill();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.xxs,
      ),
      decoration: BoxDecoration(
        color: AppColors.primary.withAlpha(40),
        borderRadius: BorderRadius.circular(AppRadius.full),
        border: Border.all(color: AppColors.primary.withAlpha(80)),
      ),
      child: Text(
        'Reading',
        style: AppTypography.caption.copyWith(
          color: AppColors.primary,
          fontWeight: FontWeight.w700,
          letterSpacing: 0.4,
        ),
      ),
    );
  }
}
