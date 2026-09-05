/// Where a series page's primary action goes, and whether it reads as
/// "Continue" or "Start Reading".
///
/// The Dart half of one shared rule; the web's is
/// `frontend/src/features/library/resume-target.ts`, and the two are meant to
/// be checked against the same table of cases. Three surfaces used to answer
/// "where was I" three different ways for the same account: this screen took
/// the LAST unfinished chapter and fell back to chapter 1, the web took the
/// FIRST unfinished one, and the home strip takes the most recently read.
///
/// The rule is FURTHEST-WINS, the same principle the server's progress merge
/// runs on (`merge_progress` in `backend/services/progress_service.py`):
///
/// 1. the HIGHEST-numbered chapter with an unfinished progress row — you are
///    furthest along there, and any earlier unfinished chapter was skimmed or
///    abandoned deliberately;
/// 2. else the LOWEST-numbered chapter with no progress row at all — the first
///    thing never opened, which is what "continue" means once every chapter
///    you have touched is finished;
/// 3. else the last chapter — everything is read, so offer the end rather than
///    sending a caught-up reader back to the beginning.
///
/// Pure, and takes the chapters already ordered, so the caller keeps whatever
/// ordering its list is rendered in.
library;

/// A chapter's stored position, or null when it was never opened.
typedef ContinueProgress = ({int lastPage, bool isCompleted});

/// The chapter to open, the page to open it at (1 for a fresh start), and
/// whether the button should say "Continue".
typedef ContinueTarget<T> = ({T chapter, int page, bool isResume});

/// Resolves [ContinueTarget] over [chaptersOldestFirst], which must be
/// ascending by chapter number (`sortSeriesChapters` with
/// `SeriesChapterSortOrder.oldest`). Returns null only for a series with no
/// chapters, which has nothing to open.
///
/// [isResume] is asked of the whole series, not of the resolved chapter: after
/// finishing chapter 1 the target is unread chapter 2, and labelling that
/// "Start Reading" would deny the chapter already read. Reading the target's
/// own row instead is how a completed chapter 1 came to be offered as
/// "Continue" and reopened at its final page.
ContinueTarget<T>? resolveContinueTarget<T>(
  List<T> chaptersOldestFirst, {
  required ContinueProgress? Function(T chapter) progressOf,
}) {
  if (chaptersOldestFirst.isEmpty) return null;

  var anyProgress = false;
  T? firstUnread;
  for (final chapter in chaptersOldestFirst) {
    if (progressOf(chapter) == null) {
      firstUnread ??= chapter;
    } else {
      anyProgress = true;
    }
  }

  for (var i = chaptersOldestFirst.length - 1; i >= 0; i--) {
    final chapter = chaptersOldestFirst[i];
    final progress = progressOf(chapter);
    if (progress != null && !progress.isCompleted) {
      return (
        chapter: chapter,
        page: progress.lastPage > 0 ? progress.lastPage : 1,
        isResume: true,
      );
    }
  }

  return (
    chapter: firstUnread ?? chaptersOldestFirst.last,
    page: 1,
    isResume: anyProgress,
  );
}
