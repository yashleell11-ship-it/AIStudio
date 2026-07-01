import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class ReaderShortcuts extends StatelessWidget {
  const ReaderShortcuts({
    super.key,
    required this.child,
    required this.onPreviousChapter,
    required this.onNextChapter,
    required this.onBookmark,
    required this.onZoomIn,
    required this.onZoomOut,
    required this.onZoomReset,
  });

  final Widget child;
  final VoidCallback onPreviousChapter;
  final VoidCallback onNextChapter;
  final VoidCallback onBookmark;
  final VoidCallback onZoomIn;
  final VoidCallback onZoomOut;
  final VoidCallback onZoomReset;

  @override
  Widget build(BuildContext context) {
    return Shortcuts(
      shortcuts: const {
        SingleActivator(LogicalKeyboardKey.keyH): _PreviousChapterIntent(),
        SingleActivator(LogicalKeyboardKey.keyL): _NextChapterIntent(),
        SingleActivator(LogicalKeyboardKey.keyB): _BookmarkIntent(),
        SingleActivator(LogicalKeyboardKey.equal): _ZoomInIntent(),
        SingleActivator(LogicalKeyboardKey.add): _ZoomInIntent(),
        SingleActivator(LogicalKeyboardKey.numpadAdd): _ZoomInIntent(),
        SingleActivator(LogicalKeyboardKey.minus): _ZoomOutIntent(),
        SingleActivator(LogicalKeyboardKey.numpadSubtract): _ZoomOutIntent(),
        SingleActivator(LogicalKeyboardKey.digit0): _ZoomResetIntent(),
        SingleActivator(LogicalKeyboardKey.numpad0): _ZoomResetIntent(),
      },
      child: Actions(
        actions: {
          _PreviousChapterIntent: CallbackAction<_PreviousChapterIntent>(
            onInvoke: (_) {
              onPreviousChapter();
              return null;
            },
          ),
          _NextChapterIntent: CallbackAction<_NextChapterIntent>(
            onInvoke: (_) {
              onNextChapter();
              return null;
            },
          ),
          _BookmarkIntent: CallbackAction<_BookmarkIntent>(
            onInvoke: (_) {
              onBookmark();
              return null;
            },
          ),
          _ZoomInIntent: CallbackAction<_ZoomInIntent>(
            onInvoke: (_) {
              onZoomIn();
              return null;
            },
          ),
          _ZoomOutIntent: CallbackAction<_ZoomOutIntent>(
            onInvoke: (_) {
              onZoomOut();
              return null;
            },
          ),
          _ZoomResetIntent: CallbackAction<_ZoomResetIntent>(
            onInvoke: (_) {
              onZoomReset();
              return null;
            },
          ),
        },
        child: Focus(autofocus: true, child: child),
      ),
    );
  }
}

class _PreviousChapterIntent extends Intent {
  const _PreviousChapterIntent();
}

class _NextChapterIntent extends Intent {
  const _NextChapterIntent();
}

class _BookmarkIntent extends Intent {
  const _BookmarkIntent();
}

class _ZoomInIntent extends Intent {
  const _ZoomInIntent();
}

class _ZoomOutIntent extends Intent {
  const _ZoomOutIntent();
}

class _ZoomResetIntent extends Intent {
  const _ZoomResetIntent();
}
