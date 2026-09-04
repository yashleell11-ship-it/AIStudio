import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/features/sources/utils/chapter_label.dart';
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

/// Which of the five distinct things a chapter row's download control can be
/// saying. They used to collapse into one disabled icon button, so a chapter
/// mid-download, one waiting its turn and one entirely on the phone were
/// pixel-identical — the reason downloading felt like it did nothing.
enum SeriesChapterDownloadPhase {
  /// Nothing on this phone for this chapter — the row offers to fetch it.
  notDownloaded,

  /// Accepted into the durable queue, not yet reached by the fetch loop.
  queued,

  /// Being fetched right now. The only phase that carries a page counter.
  downloading,

  /// Every page is on disk: readable with no network at all. Marked with a
  /// persistent badge rather than a disabled button, because "already done"
  /// and "can't press this" are different statements.
  downloaded,

  /// Bounded retries exhausted. The affordance is "retry", not "download".
  failed,
}

/// Trailing download control for one chapter row, plus the words that go with
/// it. Both series pages build this through `chapterDownloadAction()` so the
/// library and source lists can never disagree about what a state looks like.
class SeriesChapterDownloadAction {
  const SeriesChapterDownloadAction({
    required this.phase,
    this.onPressed,
    this.pagesDone = 0,
    this.pageTotal = 0,
    this.error,
    this.buttonKey,
  });

  final SeriesChapterDownloadPhase phase;

  /// Only [SeriesChapterDownloadPhase.notDownloaded] and
  /// [SeriesChapterDownloadPhase.failed] are pressable; every other phase is
  /// a status badge, so a null callback here is never the thing that
  /// communicates state.
  final VoidCallback? onPressed;

  /// Pages of this chapter already on disk and how many it has in total, live
  /// from the queue — non-zero only while this exact chapter is the one being
  /// fetched. [pageTotal] is 0 until the manifest lands, which is precisely
  /// when the bar must stay indeterminate rather than claim "0 of 0".
  final int pagesDone;
  final int pageTotal;

  /// Last failure message for [SeriesChapterDownloadPhase.failed].
  final String? error;

  final Key? buttonKey;

  /// Null means indeterminate — see [pageTotal].
  double? get progressValue =>
      pageTotal > 0 ? (pagesDone / pageTotal).clamp(0.0, 1.0) : null;

  /// The line printed under the chapter title. Deliberately a sentence rather
  /// than an icon alone: the badge answers "what state", this answers "how
  /// far along" and "why did it stop".
  String? get statusText => switch (phase) {
        SeriesChapterDownloadPhase.notDownloaded => null,
        SeriesChapterDownloadPhase.queued => 'Queued for download',
        SeriesChapterDownloadPhase.downloading => pageTotal > 0
            ? 'Downloading · page $pagesDone of $pageTotal'
            : 'Downloading · reading chapter details…',
        SeriesChapterDownloadPhase.downloaded => 'Saved offline',
        SeriesChapterDownloadPhase.failed =>
          error == null ? 'Download failed' : 'Download failed — $error',
      };

  String get tooltip => switch (phase) {
        SeriesChapterDownloadPhase.notDownloaded => 'Download Chapter',
        SeriesChapterDownloadPhase.queued => 'Queued for download',
        SeriesChapterDownloadPhase.downloading => pageTotal > 0
            ? 'Downloading — page $pagesDone of $pageTotal'
            : 'Downloading',
        SeriesChapterDownloadPhase.downloaded =>
          'Saved offline — reads with no connection',
        SeriesChapterDownloadPhase.failed => 'Retry Download',
      };
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
                      if (download != null) _DownloadStatusLine(download: download),
                    ],
                  ),
                ),
              ),
            ),
            if (download != null) _DownloadControl(download: download),
          ],
        ),
      ),
    );

    // Read chapters recede: dropping the whole card's opacity over the dark
    // background reads as a darker, muted "already read" row.
    return isRead ? Opacity(opacity: 0.6, child: card) : card;
  }
}

/// The sentence under the chapter title describing its download, and the
/// determinate bar that goes with an in-flight one. Nothing at all for a
/// chapter that has never been queued — an untouched row must stay quiet.
class _DownloadStatusLine extends StatelessWidget {
  const _DownloadStatusLine({required this.download});

  final SeriesChapterDownloadAction download;

  @override
  Widget build(BuildContext context) {
    final text = download.statusText;
    if (text == null) return const SizedBox.shrink();

    final color = switch (download.phase) {
      SeriesChapterDownloadPhase.failed => AppColors.danger,
      SeriesChapterDownloadPhase.downloaded => AppColors.success,
      SeriesChapterDownloadPhase.downloading => AppColors.primary,
      SeriesChapterDownloadPhase.queued ||
      SeriesChapterDownloadPhase.notDownloaded =>
        AppColors.muted,
    };

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(text, style: AppTypography.caption.copyWith(color: color)),
        if (download.phase == SeriesChapterDownloadPhase.downloading) ...[
          const SizedBox(height: AppSpacing.xxs),
          ClipRRect(
            borderRadius: BorderRadius.circular(AppSpacing.xs),
            child: LinearProgressIndicator(
              key: const Key('chapter-download-bar'),
              value: download.progressValue,
              minHeight: 3,
              backgroundColor: AppColors.fg.withAlpha(20),
              valueColor: const AlwaysStoppedAnimation(AppColors.primary),
            ),
          ),
        ],
      ],
    );
  }
}

/// The trailing control. A button only where there is something to press:
/// every other phase is a badge occupying the same slot, so a row never jumps
/// as a chapter moves from queued to downloading to saved.
class _DownloadControl extends StatelessWidget {
  const _DownloadControl({required this.download});

  final SeriesChapterDownloadAction download;

  @override
  Widget build(BuildContext context) {
    return switch (download.phase) {
      SeriesChapterDownloadPhase.notDownloaded => IconButton(
          key: download.buttonKey,
          tooltip: download.tooltip,
          onPressed: download.onPressed,
          icon: const Icon(Icons.download_outlined),
        ),
      SeriesChapterDownloadPhase.failed => IconButton(
          key: download.buttonKey,
          tooltip: download.tooltip,
          onPressed: download.onPressed,
          icon: const Icon(Icons.refresh, color: AppColors.danger),
        ),
      SeriesChapterDownloadPhase.queued => _DownloadBadge(
          badgeKey: download.buttonKey,
          tooltip: download.tooltip,
          child: const Icon(Icons.schedule, color: AppColors.muted, size: 20),
        ),
      SeriesChapterDownloadPhase.downloading => _DownloadBadge(
          badgeKey: download.buttonKey,
          tooltip: download.tooltip,
          child: SizedBox(
            width: 20,
            height: 20,
            child: CircularProgressIndicator(
              value: download.progressValue,
              strokeWidth: 2,
              backgroundColor: AppColors.fg.withAlpha(20),
              valueColor: const AlwaysStoppedAnimation(AppColors.primary),
            ),
          ),
        ),
      // Filled, coloured and permanent: the owner's complaint was that a
      // downloaded chapter was indistinguishable from one that merely could
      // not be pressed.
      SeriesChapterDownloadPhase.downloaded => _DownloadBadge(
          badgeKey: download.buttonKey,
          tooltip: download.tooltip,
          child: const Icon(Icons.offline_pin, color: AppColors.success, size: 22),
        ),
    };
  }
}

/// A non-interactive stand-in sized like the [IconButton] it replaces.
class _DownloadBadge extends StatelessWidget {
  const _DownloadBadge({
    required this.child,
    required this.tooltip,
    this.badgeKey,
  });

  final Widget child;
  final String tooltip;
  final Key? badgeKey;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      key: badgeKey,
      message: tooltip,
      child: SizedBox(
        width: kMinInteractiveDimension,
        height: kMinInteractiveDimension,
        child: Center(child: child),
      ),
    );
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
