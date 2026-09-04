import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/shared/widgets/series_detail/series_chapter_sort.dart';
import 'package:manhwamaniacs/shared/widgets/series_detail/series_detail_header.dart';

/// The whole series page below the app bar, shared by the library (downloaded)
/// and source (catalog) series screens.
///
/// The screens hand in *what* to show; this widget decides the order, the
/// spacing and the section headings. That is deliberate: the two pages drifted
/// into looking like different apps precisely because each maintained its own
/// composition, so the composition is the part that has to live in one place.
/// Anything genuinely one-sided (favourite, page counts and read percentage on
/// the library side; browsing a source's catalog on the other) arrives through
/// [secondaryActions] or [details] and still lands in the same slot on both.
class SeriesDetailBody extends StatelessWidget {
  const SeriesDetailBody({
    super.key,
    this.cover,
    required this.title,
    this.originalTitle,
    this.author,
    this.artist,
    this.metaLine,
    this.description,
    this.primaryAction,
    this.followAction,
    this.secondaryActions = const [],
    this.details = const [],
    required this.sortOrder,
    required this.onSortOrderChanged,
    required this.chapterTiles,
    required this.emptyChapters,
  });

  final Widget? cover;
  final String title;
  final String? originalTitle;
  final String? author;
  final String? artist;
  final String? metaLine;
  final String? description;

  /// The read call-to-action (Continue / Start Reading / Read Online).
  final Widget? primaryAction;

  /// Follow / Unfollow. Null when the series has no source to follow.
  final Widget? followAction;

  /// Download Series / Download Selected / Favorite — laid out as a wrap so a
  /// page contributing two of them and a page contributing three still read as
  /// the same row of secondary actions.
  final List<Widget> secondaryActions;

  /// Extra blocks between the actions and the chapter list: status chips, tags,
  /// genres, collection membership.
  final List<Widget> details;

  final SeriesChapterSortOrder sortOrder;
  final ValueChanged<SeriesChapterSortOrder> onSortOrderChanged;

  /// Already-built [SeriesChapterTile]s, in display order.
  final List<Widget> chapterTiles;

  /// Shown in place of the list when there are no chapters at all.
  final Widget emptyChapters;

  /// Logical width the [cover] will be painted at: the full content column,
  /// which is the page width less this widget's own horizontal padding.
  ///
  /// Exposed because the cover arrives pre-built from the screen above, which
  /// therefore has to know how wide it will end up in order to request a
  /// right-sized image — and the padding that decides that lives here.
  static double coverWidthFor(BuildContext context) =>
      MediaQuery.sizeOf(context).width - context.space.xl2 * 2;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: EdgeInsets.fromLTRB(
        context.space.xl2,
        context.space.xl2,
        context.space.xl2,
        context.space.xl2 + MediaQuery.paddingOf(context).bottom,
      ),
      children: [
        SeriesDetailHeader(
          cover: cover,
          title: title,
          originalTitle: originalTitle,
          author: author,
          artist: artist,
          metaLine: metaLine,
          description: description,
        ),
        if (primaryAction != null) ...[
          SizedBox(height: context.space.lg),
          primaryAction!,
        ],
        if (followAction != null) ...[
          SizedBox(height: context.space.lg),
          followAction!,
        ],
        if (secondaryActions.isNotEmpty) ...[
          SizedBox(height: context.space.lg),
          Wrap(
            spacing: context.space.sm,
            runSpacing: context.space.sm,
            children: secondaryActions,
          ),
        ],
        for (final detail in details) ...[
          SizedBox(height: context.space.lg),
          detail,
        ],
        SizedBox(height: context.space.xl2),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text('Chapters', style: context.text.h3),
            if (chapterTiles.isNotEmpty)
              SeriesChapterSortToggle(
                value: sortOrder,
                onChanged: onSortOrderChanged,
              ),
          ],
        ),
        SizedBox(height: context.space.md),
        if (chapterTiles.isEmpty) emptyChapters else ...chapterTiles,
      ],
    );
  }
}
