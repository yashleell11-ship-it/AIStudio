import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/features/novels/models/novel_typography.dart';
import 'package:manhwamaniacs/features/novels/utils/novel_book.dart';
import 'package:manhwamaniacs/shared/widgets/scroll_reveal.dart';
import 'package:manhwamaniacs/shared/widgets/series_cover_image.dart';

/// A shelf of books, in place of the poster grid.
///
/// The grid asks the cover to carry the identity, and three columns of them
/// on a phone leaves room for a title and nothing else. That is right for
/// manhwa, whose art IS the recognition. It is wrong for novels: a web-novel
/// aggregator's cover is usually a generated placeholder, so a grid of them is
/// a grid of interchangeable rectangles.
///
/// What a reader actually recognises a novel by is its title, its author and
/// its length — so a row leads with those, in the serif that carries the mode,
/// with the cover kept small and to the side. Kept rather than dropped,
/// because when the art IS real it still helps.
class NovelShelf extends StatelessWidget {
  const NovelShelf({
    super.key,
    required this.itemCount,
    required this.bookAt,
  });

  final int itemCount;
  final ShelfBook Function(int index) bookAt;

  @override
  Widget build(BuildContext context) {
    return SliverList.separated(
      itemCount: itemCount,
      separatorBuilder: (context, index) => Divider(
        height: 1,
        thickness: 1,
        indent: context.space.lg,
        endIndent: context.space.lg,
        color: context.colors.border,
      ),
      itemBuilder: (context, index) => ScrollReveal(
        index: index,
        child: _ShelfRow(book: bookAt(index)),
      ),
    );
  }
}

/// One book on a shelf.
///
/// A view model rather than a source shape on purpose: browse rows and library
/// rows carry different fields, and the shelf renders both.
class ShelfBook {
  const ShelfBook({
    required this.title,
    required this.author,
    required this.description,
    required this.chapterCount,
    required this.status,
    required this.coverUrl,
    required this.onTap,
    this.note,
  });

  final String title;
  final String? author;
  final String? description;
  final int? chapterCount;

  /// Publication status as the source words it ("ongoing", "Completed").
  final String? status;

  /// Already resolved to a fetchable URL by the caller.
  ///
  /// A source with no cover returns an EMPTY STRING, which resolves against the
  /// API base into a URL that loads the backend root as an image. On the manga
  /// side a missing cover is rare enough never to have mattered; on a
  /// public-domain novel archive it is routine, so the caller passes null and
  /// the row draws its own mark instead.
  final String? coverUrl;

  /// Anything shelf-specific worth a line: "Reading · 42%", "Favourite".
  final String? note;

  final VoidCallback onTap;

  /// The one metadata line under the title, as parts to join.
  ///
  /// Empty parts are dropped rather than rendered as stray separators — a
  /// source that reports no author and no chapter count should produce a title
  /// with nothing under it, not "by  ·  · ".
  List<String> get metaParts => [
        byline(author),
        formatChapterCount(chapterCount),
        formatStatus(status),
        if (note != null && note!.trim().isNotEmpty) note!.trim(),
      ].whereType<String>().toList();
}

class _ShelfRow extends StatelessWidget {
  const _ShelfRow({required this.book});

  final ShelfBook book;

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    const serif = kNovelSerifStack;
    final meta = book.metaParts.join('  ·  ');
    final blurb = shelfBlurb(book.description);

    return InkWell(
      onTap: book.onTap,
      child: Padding(
        padding: EdgeInsets.symmetric(
          horizontal: context.space.lg,
          vertical: context.space.md,
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    book.title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontFamily: serif.first,
                      fontFamilyFallback: serif.sublist(1),
                      fontSize: 17,
                      height: 1.25,
                      fontWeight: FontWeight.w600,
                      color: colors.fg,
                    ),
                  ),
                  if (meta.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(top: 4),
                      child: Text(
                        meta,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(fontSize: 12, color: colors.muted),
                      ),
                    ),
                  if (blurb != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 6),
                      child: Text(
                        blurb,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 13,
                          height: 1.45,
                          color: colors.muted,
                        ),
                      ),
                    ),
                ],
              ),
            ),
            SizedBox(width: context.space.md),
            _Plate(coverUrl: book.coverUrl, title: book.title),
          ],
        ),
      ),
    );
  }
}

/// The small cover, or a plate standing in for one.
///
/// The stand-in is a bordered rectangle carrying the book's initial rather
/// than a broken-image glyph: on an archive where most books have no art, a
/// column of broken images reads as a broken app.
class _Plate extends StatelessWidget {
  const _Plate({required this.coverUrl, required this.title});

  final String? coverUrl;
  final String title;

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    const size = Size(46, 66);

    if (coverUrl != null && coverUrl!.isNotEmpty) {
      return ClipRRect(
        borderRadius: BorderRadius.circular(context.radii.sm),
        child: SizedBox(
          width: size.width,
          height: size.height,
          child: SeriesCoverImage(
            url: coverUrl!,
            displayWidth: size.width,
            borderRadius: 0,
          ),
        ),
      );
    }

    final initial = title.trim().isEmpty ? '·' : title.trim()[0].toUpperCase();
    return Container(
      width: size.width,
      height: size.height,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(context.radii.sm),
        color: colors.surface2,
        border: Border.all(color: colors.border),
      ),
      child: Text(
        initial,
        style: TextStyle(
          fontFamily: kNovelSerifStack.first,
          fontFamilyFallback: kNovelSerifStack.sublist(1),
          fontSize: 20,
          color: colors.muted,
        ),
      ),
    );
  }
}
