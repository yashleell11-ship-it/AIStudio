import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/downloads/models/chapter_selection.dart';

SelectableChapter _chapter(
  double number, {
  bool isRead = false,
  bool isDownloaded = false,
}) =>
    (
      key: 'ch-${number.toStringAsFixed(0)}',
      number: number,
      title: 'Chapter ${number.toStringAsFixed(0)}',
      isRead: isRead,
      isDownloaded: isDownloaded,
    );

void main() {
  group('range helpers', () {
    test('"next 10" takes the next ten unread chapters not already on disk',
        () {
      final chapters = [
        for (var i = 1; i <= 30; i++)
          _chapter(i.toDouble(), isRead: i <= 5, isDownloaded: i >= 6 && i <= 8),
      ];

      final keys = nextUnreadUndownloadedKeys(chapters);

      expect(keys, hasLength(10));
      // 1-5 are read, 6-8 are already downloaded: the next ten start at 9.
      expect(keys.first, 'ch-9');
      expect(keys.last, 'ch-18');
    });

    test('"next 10" hands back fewer when the series has fewer left', () {
      final chapters = [for (var i = 1; i <= 3; i++) _chapter(i.toDouble())];
      expect(nextUnreadUndownloadedKeys(chapters), hasLength(3));
    });

    test('"all unread" skips read and already-downloaded chapters', () {
      final chapters = [
        _chapter(1, isRead: true),
        _chapter(2, isDownloaded: true),
        _chapter(3),
        _chapter(4, isRead: true, isDownloaded: true),
        _chapter(5),
      ];
      expect(unreadUndownloadedKeys(chapters), ['ch-3', 'ch-5']);
    });

    test('"all" keeps read chapters — a re-read still wants the whole thing',
        () {
      final chapters = [
        _chapter(1, isRead: true),
        _chapter(2, isDownloaded: true),
        _chapter(3),
      ];
      expect(undownloadedKeys(chapters), ['ch-1', 'ch-3']);
    });

    test('reading order is the caller\'s, never re-sorted here', () {
      // Handed newest-first on purpose: the helpers must respect the order
      // given, because "next" means next-to-read and the visible list's sort
      // toggle has nothing to do with it.
      final chapters = [_chapter(3), _chapter(2), _chapter(1)];
      expect(unreadUndownloadedKeys(chapters), ['ch-3', 'ch-2', 'ch-1']);
    });

    test('a fully-downloaded series offers nothing to any range', () {
      final chapters = [
        for (var i = 1; i <= 5; i++) _chapter(i.toDouble(), isDownloaded: true),
      ];
      expect(nextUnreadUndownloadedKeys(chapters), isEmpty);
      expect(unreadUndownloadedKeys(chapters), isEmpty);
      expect(undownloadedKeys(chapters), isEmpty);
    });
  });

  group('ChapterSelectionController', () {
    test('starts idle with nothing selected', () {
      final controller = ChapterSelectionController();
      addTearDown(controller.dispose);
      expect(controller.isActive, isFalse);
      expect(controller.count, 0);
    });

    test('toggling adds then removes', () {
      final controller = ChapterSelectionController();
      addTearDown(controller.dispose);
      controller
        ..begin()
        ..toggle('ch-1')
        ..toggle('ch-2');
      expect(controller.selected, {'ch-1', 'ch-2'});
      controller.toggle('ch-1');
      expect(controller.selected, {'ch-2'});
    });

    test('a range REPLACES the selection — "next 10" twice is ten, not twenty',
        () {
      final controller = ChapterSelectionController();
      addTearDown(controller.dispose);
      controller.replaceWith(['a', 'b', 'c']);
      controller.replaceWith(['a', 'b', 'c']);
      expect(controller.count, 3);
    });

    test('a range also enters selection mode, so one tap is enough', () {
      final controller = ChapterSelectionController();
      addTearDown(controller.dispose);
      expect(controller.isActive, isFalse);
      controller.replaceWith(['a']);
      expect(controller.isActive, isTrue);
    });

    test('ending forgets the selection, so re-entering starts clean', () {
      final controller = ChapterSelectionController();
      addTearDown(controller.dispose);
      controller
        ..begin()
        ..toggle('ch-1')
        ..end();
      expect(controller.isActive, isFalse);
      expect(controller.count, 0);
      controller.begin();
      expect(controller.count, 0);
    });

    test('every state change notifies — the rows and the bar must agree', () {
      final controller = ChapterSelectionController();
      addTearDown(controller.dispose);
      var notifications = 0;
      controller.addListener(() => notifications++);

      controller.begin();
      controller.toggle('ch-1');
      controller.replaceWith(['ch-2', 'ch-3']);
      controller.clearSelection();
      controller.end();

      expect(notifications, 5);
    });

    test('a no-op does not notify', () {
      final controller = ChapterSelectionController();
      addTearDown(controller.dispose);
      var notifications = 0;
      controller.addListener(() => notifications++);

      controller.clearSelection(); // nothing selected
      controller.end(); // already idle and empty
      expect(notifications, 0);
    });
  });
}
