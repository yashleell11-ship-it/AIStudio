import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/library/utils/continue_target.dart';

/// A chapter reduced to what the rule actually looks at.
typedef _Chapter = ({int number, ContinueProgress? progress});

_Chapter _unread(int number) => (number: number, progress: null);

_Chapter _read(int number, {required int page, bool done = false}) =>
    (number: number, progress: (lastPage: page, isCompleted: done));

ContinueTarget<_Chapter>? _resolve(List<_Chapter> ascending) =>
    resolveContinueTarget(ascending, progressOf: (chapter) => chapter.progress);

void main() {
  // The same table of cases as `frontend/src/features/library/resume-target.ts`
  // — the two clients answer "where was I" with one rule or they answer it
  // differently, which is the bug this file exists to close.
  group('resolveContinueTarget', () {
    test('a series with no chapters has nothing to open', () {
      expect(_resolve(const []), isNull);
    });

    test('nothing read yet starts at the first chapter', () {
      final target = _resolve([_unread(1), _unread(2), _unread(3)]);
      expect(target!.chapter.number, 1);
      expect(target.page, 1);
      expect(target.isResume, isFalse);
    });

    test('an unfinished chapter resumes at its stored page', () {
      final target = _resolve([_read(1, page: 5), _unread(2)]);
      expect(target!.chapter.number, 1);
      expect(target.page, 5);
      expect(target.isResume, isTrue);
    });

    test('finishing a chapter cleanly advances to the next unread one', () {
      // The regression: chapter 1 finished and closed on its last page (no
      // auto-advance) used to fall back to `first chapter`, so Continue
      // reopened chapter 1 at its end.
      final target = _resolve([
        _read(1, page: 20, done: true),
        _unread(2),
        _unread(3),
      ]);
      expect(target!.chapter.number, 2);
      expect(target.page, 1);
      expect(target.isResume, isTrue);
    });

    test('the furthest unfinished chapter wins over an earlier skimmed one',
        () {
      final target = _resolve([
        _read(1, page: 20, done: true),
        _read(5, page: 3),
        _read(40, page: 12),
      ]);
      expect(target!.chapter.number, 40);
      expect(target.page, 12);
    });

    test('an unfinished chapter beats a later chapter that was never opened',
        () {
      final target = _resolve([
        _read(1, page: 20, done: true),
        _read(2, page: 4),
        _unread(3),
      ]);
      expect(target!.chapter.number, 2);
    });

    test('a fully read series reopens the last chapter at the top', () {
      final target = _resolve([
        _read(1, page: 20, done: true),
        _read(2, page: 20, done: true),
        _read(3, page: 20, done: true),
      ]);
      expect(target!.chapter.number, 3);
      // Never chapter 1, and never dropped on the final page of the last one.
      expect(target.page, 1);
      expect(target.isResume, isTrue);
    });

    test('a gap left behind is offered before a finished later chapter', () {
      final target = _resolve([
        _read(1, page: 20, done: true),
        _unread(2),
        _read(3, page: 20, done: true),
      ]);
      expect(target!.chapter.number, 2);
    });

    test('reading history anywhere in the series reads as Continue', () {
      final target = _resolve([_read(1, page: 20, done: true), _unread(2)]);
      // The target chapter has no progress row of its own, but a chapter of
      // history must not be labelled "Start Reading".
      expect(target!.isResume, isTrue);
    });

    test('a stored page of zero opens at page 1 rather than page 0', () {
      final target = _resolve([_read(1, page: 0)]);
      expect(target!.page, 1);
    });
  });
}
