import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/downloads/models/download_item.dart';
import 'package:manhwamaniacs/features/downloads/models/series_download_group.dart';
import 'package:manhwamaniacs/features/downloads/utils/download_grouping.dart';
import 'package:manhwamaniacs/features/downloads/widgets/downloads_widgets.dart';

DownloadItem _item({
  required int id,
  String status = 'queued',
}) {
  return DownloadItem(
    id: id,
    source: 'test',
    seriesId: 'solo',
    chapterId: 'ch-$id',
    seriesTitle: 'Solo Leveling',
    chapterTitle: 'Chapter $id',
    status: status,
    progress: 0,
    pagesDone: 0,
    pagesTotal: 20,
    bytesDownloaded: 0,
    createdAt: DateTime.utc(2024),
    updatedAt: DateTime.utc(2024),
    priority: id,
    retryCount: 0,
  );
}

SeriesDownloadGroup _group(List<DownloadItem> items) {
  return SeriesDownloadGroup(
    key: 'test:solo',
    source: 'test',
    seriesId: 'solo',
    seriesTitle: 'Solo Leveling',
    items: items,
    active: items.where((i) => i.isDownloading).length,
    queued: items.where((i) => i.isQueued).length,
    completed: items.where((i) => i.isCompleted).length,
    failed: items.where((i) => i.isFailed).length,
    paused: items.where((i) => i.isPaused).length,
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  Widget wrap(Widget child) => MaterialApp(
        home: Scaffold(body: SingleChildScrollView(child: child)),
      );

  testWidgets('shows no reorder arrows when onMoveItem is not provided',
      (tester) async {
    final items = [_item(id: 1), _item(id: 2)];
    await tester.pumpWidget(
      wrap(SeriesGroupCard(
        group: _group(items),
        filter: DownloadFilterTab.all,
        busy: false,
        onPauseSeries: () {},
        onResumeSeries: () {},
        onCancelSeries: () {},
        onPauseItem: (_) {},
        onResumeItem: (_) {},
        onCancelItem: (_) {},
        onRetryItem: (_) {},
      ),),
    );

    expect(find.byIcon(Icons.keyboard_arrow_up), findsNothing);
    expect(find.byIcon(Icons.keyboard_arrow_down), findsNothing);
  });

  testWidgets(
      'the first queued item can only move down, the last only up',
      (tester) async {
    final items = [_item(id: 1), _item(id: 2), _item(id: 3)];
    (int, String)? moved;
    await tester.pumpWidget(
      wrap(SeriesGroupCard(
        group: _group(items),
        filter: DownloadFilterTab.all,
        busy: false,
        onPauseSeries: () {},
        onResumeSeries: () {},
        onCancelSeries: () {},
        onPauseItem: (_) {},
        onResumeItem: (_) {},
        onCancelItem: (_) {},
        onRetryItem: (_) {},
        onMoveItem: (id, direction) => moved = (id, direction),
      ),),
    );

    // 3 items => 3 up + 3 down buttons rendered, but the first item's "up"
    // and the last item's "down" must be disabled (onPressed: null).
    final upButtons = tester.widgetList<IconButton>(
      find.ancestor(
        of: find.byIcon(Icons.keyboard_arrow_up),
        matching: find.byType(IconButton),
      ),
    );
    final downButtons = tester.widgetList<IconButton>(
      find.ancestor(
        of: find.byIcon(Icons.keyboard_arrow_down),
        matching: find.byType(IconButton),
      ),
    );

    expect(upButtons.length, 3);
    expect(downButtons.length, 3);
    expect(upButtons.first.onPressed, isNull); // item 1: can't move up
    expect(upButtons.last.onPressed, isNotNull); // item 3: can move up
    expect(downButtons.first.onPressed, isNotNull); // item 1: can move down
    expect(downButtons.last.onPressed, isNull); // item 3: can't move down

    await tester.tap(find.byIcon(Icons.keyboard_arrow_down).first);
    await tester.pump();
    expect(moved, (1, 'down'));
  });

  testWidgets(
      'paused/downloading items never show reorder arrows, even with '
      'queued siblings that do', (tester) async {
    final items = [
      _item(id: 1),
      _item(id: 2, status: 'paused'),
      _item(id: 3, status: 'downloading'),
      _item(id: 4),
    ];
    await tester.pumpWidget(
      wrap(SeriesGroupCard(
        group: _group(items),
        filter: DownloadFilterTab.all,
        busy: false,
        onPauseSeries: () {},
        onResumeSeries: () {},
        onCancelSeries: () {},
        onPauseItem: (_) {},
        onResumeItem: (_) {},
        onCancelItem: (_) {},
        onRetryItem: (_) {},
        onMoveItem: (_, __) {},
      ),),
    );

    // Only the two queued items (ids 1 and 4) get reorder controls at all --
    // the paused and downloading ones show none, not even disabled.
    final upButtons = tester.widgetList<IconButton>(
      find.ancestor(
        of: find.byIcon(Icons.keyboard_arrow_up),
        matching: find.byType(IconButton),
      ),
    );
    expect(upButtons.length, 2);
  });

  testWidgets(
      'a lone queued item (nothing to reorder against) shows no arrows at all',
      (tester) async {
    final items = [_item(id: 1), _item(id: 2, status: 'paused')];
    await tester.pumpWidget(
      wrap(SeriesGroupCard(
        group: _group(items),
        filter: DownloadFilterTab.all,
        busy: false,
        onPauseSeries: () {},
        onResumeSeries: () {},
        onCancelSeries: () {},
        onPauseItem: (_) {},
        onResumeItem: (_) {},
        onCancelItem: (_) {},
        onRetryItem: (_) {},
        onMoveItem: (_, __) {},
      ),),
    );

    expect(find.byIcon(Icons.keyboard_arrow_up), findsNothing);
    expect(find.byIcon(Icons.keyboard_arrow_down), findsNothing);
  });
}
