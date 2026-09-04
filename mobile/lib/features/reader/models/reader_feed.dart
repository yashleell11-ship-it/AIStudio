import 'package:flutter/foundation.dart';
import 'package:manhwamaniacs/features/reader/models/reader_chapter.dart';
import 'package:manhwamaniacs/features/reader/models/reader_page.dart';

/// A run of consecutive chapters presented to the reader as **one continuous
/// page list** (spec R1 and R2).
///
/// The owner's words for R1: "it should feel like scolling so i can view the
/// chap 1 last and chap 2 starting not like i go to chapter 2 directly". The
/// only way a boundary stops being a transition is if there is no boundary in
/// the widget tree to begin with — so the reader does not render "a chapter",
/// it renders a flat list of pages that happens to know which chapter each
/// page belongs to.
///
/// One chapter is the ordinary case and costs nothing: [ReaderFeed.single] is
/// exactly today's reader, and every index question below answers about that
/// one chapter. Read-all (R2) is the same object with a window of chapters in
/// it, grown and trimmed as the reader moves — which is why there is one
/// mechanism here and not two.
///
/// Immutable: growing or trimming produces a new feed, so a widget can compare
/// the old and new and work out exactly how far the content above the viewport
/// moved (see `ReaderContent`'s scroll correction). A mutable list would make
/// that difference unrecoverable.
@immutable
class ReaderFeed {
  ReaderFeed._(this.chapters)
      : pages = [for (final chapter in chapters) ...chapter.pages],
        _chapterOfPage = [
          for (var c = 0; c < chapters.length; c++)
            for (var p = 0; p < chapters[c].pages.length; p++) c,
        ],
        _starts = _startIndices(chapters);

  /// One chapter — today's reader, unchanged.
  factory ReaderFeed.single(ReaderChapter chapter) => ReaderFeed._([chapter]);

  /// Several chapters in reading order. Duplicates by chapter id are dropped
  /// (first wins): a feed that held the same chapter twice would double every
  /// page of it and put the reader's progress in two places at once.
  factory ReaderFeed.of(List<ReaderChapter> chapters) {
    final seen = <String>{};
    return ReaderFeed._([
      for (final chapter in chapters)
        if (seen.add(chapter.id)) chapter,
    ]);
  }

  /// In reading order, oldest first — the order the pages are concatenated in.
  final List<ReaderChapter> chapters;

  /// Every chapter's pages, end to end. This is what the list renders and what
  /// the page geometry is indexed by.
  final List<ReaderPage> pages;

  final List<int> _chapterOfPage;
  final List<int> _starts;

  static List<int> _startIndices(List<ReaderChapter> chapters) {
    final starts = <int>[];
    var offset = 0;
    for (final chapter in chapters) {
      starts.add(offset);
      offset += chapter.pages.length;
    }
    return starts;
  }

  int get length => pages.length;

  bool get isEmpty => pages.isEmpty;

  /// True while this is an ordinary single-chapter read. Several behaviours
  /// (scroll persistence, the page counter's meaning) are identical either way
  /// but are worth being able to name.
  bool get isSingleChapter => chapters.length == 1;

  bool contains(String chapterId) =>
      chapters.any((chapter) => chapter.id == chapterId);

  int indexOfChapter(String chapterId) =>
      chapters.indexWhere((chapter) => chapter.id == chapterId);

  /// Which chapter page [flatIndex] belongs to. Clamped rather than throwing:
  /// this is asked from scroll handlers during a feed change, where an index
  /// can briefly be one past the end.
  int chapterIndexAt(int flatIndex) {
    if (_chapterOfPage.isEmpty) return 0;
    return _chapterOfPage[flatIndex.clamp(0, _chapterOfPage.length - 1)];
  }

  ReaderChapter chapterAt(int flatIndex) => chapters[chapterIndexAt(flatIndex)];

  /// The 1-based page number **within its own chapter** — what progress is
  /// recorded against, so reading into chapter 12 of a 300-chapter feed
  /// records chapter 12 page N and resume lands there.
  int pageWithinChapterAt(int flatIndex) {
    if (pages.isEmpty) return 1;
    final index = flatIndex.clamp(0, pages.length - 1);
    return index - _starts[_chapterOfPage[index]] + 1;
  }

  /// Flat index of the first page of chapter [chapterIndex].
  int startOfChapter(int chapterIndex) =>
      _starts[chapterIndex.clamp(0, _starts.length - 1)];

  /// True when [flatIndex] is the first page of a chapter that is **not** the
  /// first in the feed — i.e. exactly where a seam divider belongs. The first
  /// chapter gets no divider: nothing was crossed to reach it.
  bool startsLaterChapter(int flatIndex) {
    for (var c = 1; c < _starts.length; c++) {
      if (_starts[c] == flatIndex) return true;
    }
    return false;
  }

  /// Flat index of [page] (1-based) within [chapterId], or null when the feed
  /// does not hold that chapter.
  int? flatIndexOf({required String chapterId, required int page}) {
    final chapterIndex = indexOfChapter(chapterId);
    if (chapterIndex < 0) return null;
    final chapter = chapters[chapterIndex];
    if (chapter.pages.isEmpty) return null;
    final local = page.clamp(1, chapter.pages.length);
    return _starts[chapterIndex] + local - 1;
  }

  /// The same feed with [chapter] added after the last one — the forward seam.
  /// A chapter already in the feed is ignored, so a double-fire of the
  /// boundary trigger cannot duplicate it.
  ReaderFeed withAppended(ReaderChapter chapter) =>
      contains(chapter.id) ? this : ReaderFeed._([...chapters, chapter]);

  /// The same feed with [chapter] added before the first — the backward seam.
  /// **Every page index shifts** by the new chapter's page count, which is why
  /// the caller has to correct the scroll offset by the extent it occupies.
  ReaderFeed withPrepended(ReaderChapter chapter) =>
      contains(chapter.id) ? this : ReaderFeed._([chapter, ...chapters]);

  /// Drops the first [count] chapters — Read-all's release of what is far
  /// behind. Never drops the last chapter: a feed with no pages has nothing to
  /// render and nowhere to put the reader.
  ReaderFeed withoutLeadingChapters(int count) {
    final drop = count.clamp(0, chapters.length - 1);
    if (drop <= 0) return this;
    return ReaderFeed._(chapters.sublist(drop));
  }

  /// Drops the last [count] chapters — the other half of the window, for a
  /// reader who scrolled a long way back.
  ReaderFeed withoutTrailingChapters(int count) {
    final drop = count.clamp(0, chapters.length - 1);
    if (drop <= 0) return this;
    return ReaderFeed._(chapters.sublist(0, chapters.length - drop));
  }
}
