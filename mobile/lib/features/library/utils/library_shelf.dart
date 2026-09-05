/// The library's own rows, shelved.
///
/// Two surfaces show a followed novel — the Library tab and the browse screen
/// under it — and both used to hand it to the poster grid, which is the one
/// presentation a novel cannot survive: an aggregator's cover is a generated
/// placeholder, so a shelf of books came out as a grid of identical
/// rectangles. They both go through [libraryShelfBook] instead, so the tab and
/// the browse screen cannot drift into describing the same book two ways.
///
/// Mirrors `frontend/src/features/library/components/LibraryShelfView.tsx` and
/// `LibraryView.tsx`, which build the same view model for the web shelf.
library;

import 'package:flutter/foundation.dart';
import 'package:manhwamaniacs/features/library/models/followed_series.dart';
import 'package:manhwamaniacs/features/library/utils/cover_url.dart';
import 'package:manhwamaniacs/features/library/utils/series_display.dart';
import 'package:manhwamaniacs/features/novels/utils/novel_book.dart';
import 'package:manhwamaniacs/features/novels/widgets/novel_shelf.dart';

/// One followed book as a shelf row.
///
/// [ShelfBook.author], [ShelfBook.description] and [ShelfBook.status] are
/// null and not "unknown": a follow row carries none of them — they live on
/// the source, not on the follow — so the row says what the library actually
/// knows (how long the book is, where the reader put it, what is waiting) and
/// invents nothing. A browse shelf, which does have the source's answer, fills
/// those in itself.
ShelfBook libraryShelfBook(
  FollowedSeries series, {
  required String apiBaseUrl,
  required VoidCallback onTap,
  VoidCallback? onLongPress,
  String? note,
  bool selected = false,
  int unreadCount = 0,
}) {
  return ShelfBook(
    title: series.title,
    author: null,
    description: null,
    chapterCount: series.chapterCount,
    status: null,
    // Null rather than the empty string a coverless follow carries: the row
    // draws its own plate for a book with no art, which on a novel archive is
    // most of them.
    coverUrl: followedSeriesCoverUrl(apiBaseUrl, series),
    note: note,
    onTap: onTap,
    onLongPress: onLongPress,
    selected: selected,
    isFavorite: series.isFavorite,
    unreadCount: unreadCount,
  );
}

/// "Reading", "Plan to read" — where the reader has put this book.
///
/// The poster grid sets the same word under a cover, in its own line, where
/// lowercase reads as a label. On a shelf it is set inside a run of metadata
/// beside "412 chapters", where lowercase reads as a typo.
String? readingStatusNote(String readingStatus) =>
    formatStatus(readingStatusLabel(readingStatus));

/// "Latest: Chapter 121" — the newest chapter this profile has been notified
/// about, or null when the book has never produced a notification.
///
/// Deliberately not a chapter *count*: the count is [ShelfBook.chapterCount]'s
/// job and it is stale-or-zero until the backend's update checker has run,
/// while this comes from the notifications the Library tab has already loaded.
String? latestChapterNote(String? latestChapterLabel) {
  final trimmed = latestChapterLabel?.trim();
  return (trimmed == null || trimmed.isEmpty) ? null : 'Latest: $trimmed';
}
