import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/features/downloads/models/queue_download_response.dart';
import 'package:manhwamaniacs/features/downloads/utils/queue_download_feedback.dart';

const _bulkQueue = QueueDownloadResponse(queued: [1, 2, 3], skipped: []);

/// A screen with one button that asks for the queue confirmation, so a test can
/// trigger it from whichever route it is mounted on.
class _QueuePage extends StatelessWidget {
  const _QueuePage({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: ElevatedButton(
          onPressed: () => showQueueDownloadSnackBar(context, _bulkQueue),
          child: Text(label),
        ),
      ),
    );
  }
}

/// Router with the two shapes that matter: a series page (where a download is
/// normally started) and the reader it pushes to.
GoRouter _buildRouter({required String initialLocation}) {
  return GoRouter(
    initialLocation: initialLocation,
    routes: [
      GoRoute(
        path: '/library/:seriesId',
        builder: (_, __) => const _QueuePage(label: 'Queue from series'),
        routes: [
          GoRoute(
            path: 'chapters/:chapterId/read',
            builder: (_, __) => const _QueuePage(label: 'Queue from reader'),
          ),
        ],
      ),
    ],
  );
}

Future<GoRouter> _pumpApp(
  WidgetTester tester, {
  required String initialLocation,
}) async {
  final router = _buildRouter(initialLocation: initialLocation);
  await tester.pumpWidget(MaterialApp.router(routerConfig: router));
  await tester.pumpAndSettle();
  return router;
}

void main() {
  group('queueDownloadFeedbackMessage', () {
    test('shows queued and skipped counts', () {
      final message = queueDownloadFeedbackMessage(
        const QueueDownloadResponse(
          queued: [1, 2],
          skipped: ['ch-3'],
        ),
      );

      expect(message, 'Queued 2 chapters\nSkipped 1 already downloaded');
    });

    test('shows only queued when nothing skipped', () {
      final message = queueDownloadFeedbackMessage(
        const QueueDownloadResponse(queued: [1], skipped: []),
      );

      expect(message, 'Queued 1 chapter');
    });

    test('shows only skipped when nothing queued', () {
      final message = queueDownloadFeedbackMessage(
        const QueueDownloadResponse(queued: [], skipped: ['ch-1', 'ch-2']),
      );

      expect(message, 'Skipped 2 already downloaded');
    });

    test('shows fallback when response is empty', () {
      final message = queueDownloadFeedbackMessage(
        const QueueDownloadResponse(queued: [], skipped: []),
      );

      expect(message, 'No chapters queued');
    });
  });

  group('shouldShowQueueDownloadFeedback', () {
    test('stays silent for a clean single-chapter queue', () {
      // The tapped row already flips to its downloading state — that *is* the
      // confirmation, and it does not cover the page.
      expect(
        shouldShowQueueDownloadFeedback(
          const QueueDownloadResponse(queued: [1], skipped: []),
        ),
        isFalse,
      );
    });

    test('speaks up for a bulk queue', () {
      expect(shouldShowQueueDownloadFeedback(_bulkQueue), isTrue);
    });

    test('speaks up when a chapter was skipped', () {
      // Nothing else on screen explains why a tap appeared to do nothing.
      expect(
        shouldShowQueueDownloadFeedback(
          const QueueDownloadResponse(queued: [1], skipped: ['ch-2']),
        ),
        isTrue,
      );
      expect(
        shouldShowQueueDownloadFeedback(
          const QueueDownloadResponse(queued: [], skipped: ['ch-2']),
        ),
        isTrue,
      );
    });

    test('speaks up when nothing happened at all', () {
      expect(
        shouldShowQueueDownloadFeedback(
          const QueueDownloadResponse(queued: [], skipped: []),
        ),
        isTrue,
      );
    });
  });

  group('isReaderRoute', () {
    test('matches both reader destinations', () {
      expect(isReaderRoute('/library/12/chapters/34/read'), isTrue);
      expect(
        isReaderRoute('/sources/toonily/series/some-series/chapters/ch-1/read'),
        isTrue,
      );
    });

    test('ignores query strings and fragments', () {
      expect(isReaderRoute('/library/12/chapters/34/read?page=4'), isTrue);
      expect(isReaderRoute('/library/12/chapters/34/read#top'), isTrue);
    });

    test('does not match the screens a download is normally started from', () {
      expect(isReaderRoute('/library/12'), isFalse);
      expect(isReaderRoute('/sources/toonily/series/some-series'), isFalse);
      expect(isReaderRoute('/downloads'), isFalse);
    });

    test('survives a percent-encoded id that Uri.parse would reject', () {
      // Source series/chapter ids are opaque strings; a stray "%" must not turn
      // a should-I-stay-quiet check into a FormatException.
      expect(isReaderRoute('/sources/x/series/100%/chapters/1/read'), isTrue);
    });
  });

  group('showQueueDownloadSnackBar', () {
    testWidgets('never appears while the reader is open', (tester) async {
      await _pumpApp(tester, initialLocation: '/library/12/chapters/34/read');

      await tester.tap(find.text('Queue from reader'));
      await tester.pump();

      expect(find.byType(SnackBar), findsNothing);
      expect(find.text('Queued 3 chapters'), findsNothing);
    });

    testWidgets('does appear on the series page it was requested from',
        (tester) async {
      await _pumpApp(tester, initialLocation: '/library/12');

      await tester.tap(find.text('Queue from series'));
      await tester.pump();

      expect(find.text('Queued 3 chapters'), findsOneWidget);
    });

    testWidgets('does not follow the user into the reader', (tester) async {
      final router = await _pumpApp(tester, initialLocation: '/library/12');

      await tester.tap(find.text('Queue from series'));
      await tester.pump();
      expect(find.text('Queued 3 chapters'), findsOneWidget);

      // Same trip the owner made: start a download, then open a chapter well
      // inside the snack bar's lifetime.
      unawaited(router.push('/library/12/chapters/34/read'));
      await tester.pumpAndSettle();

      expect(find.text('Queued 3 chapters'), findsNothing);
      expect(find.byType(SnackBar), findsNothing);
    });

    testWidgets('never stacks — repeated taps replace, they do not queue up',
        (tester) async {
      await _pumpApp(tester, initialLocation: '/library/12');

      for (var i = 0; i < 4; i++) {
        await tester.tap(find.text('Queue from series'));
        await tester.pump();
      }

      // Settle the entry animation, then let exactly one lifetime elapse.
      await tester.pumpAndSettle();
      expect(find.byType(SnackBar), findsOneWidget);
      expect(find.text('Queued 3 chapters'), findsOneWidget);

      // Four taps used to mean four consecutive 4s bars — 16 seconds of
      // banner, one after another. A single lifetime must clear the lot.
      await tester.pump(queueDownloadSnackBarDuration);
      await tester.pumpAndSettle();
      expect(find.byType(SnackBar), findsNothing);
    });

    testWidgets('clears itself well before the old 4s default', (tester) async {
      await _pumpApp(tester, initialLocation: '/library/12');

      await tester.tap(find.text('Queue from series'));
      await tester.pumpAndSettle();
      expect(find.byType(SnackBar), findsOneWidget);

      // Flutter's default is 4s; anything close to that is what the owner
      // photographed sitting over his page.
      await tester.pump(const Duration(seconds: 2));
      await tester.pumpAndSettle();
      expect(find.byType(SnackBar), findsNothing);
    });
  });
}
