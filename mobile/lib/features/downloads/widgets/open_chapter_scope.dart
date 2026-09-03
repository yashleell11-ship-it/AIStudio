import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/downloads/models/chapter_identity.dart';
import 'package:manhwamaniacs/features/downloads/providers/currently_open_chapter_provider.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/services/retention_maintenance.dart'
    show ScopedChapterIdentity;

/// Marks [chapterId] as "currently open" for as long as this widget is in
/// the tree — wraps both reader entry points (the manifest-driven library
/// reader and the online source reader) so the retention sweep and cap
/// eviction can never delete a chapter someone is actively reading, no
/// matter how expired its timer or how tight the storage pressure.
///
/// Also clears the chapter's read-then-expire stamp on open: "re-reading
/// cancels it" (spec §3) — a chapter finished long enough ago to be due for
/// deletion must not vanish out from under a deliberate re-read. A no-op
/// when there is no active scope, or when [chapterId] was never downloaded
/// (nothing to protect or un-stamp in either case).
class OpenChapterScope extends ConsumerStatefulWidget {
  const OpenChapterScope({
    super.key,
    required this.chapterId,
    required this.child,
  });

  final ChapterIdentity chapterId;
  final Widget child;

  @override
  ConsumerState<OpenChapterScope> createState() => _OpenChapterScopeState();
}

class _OpenChapterScopeState extends ConsumerState<OpenChapterScope> {
  ScopedChapterIdentity? _claimed;

  // Resolved once and reused rather than a fresh `ref.read(...)` later: by
  // the time `dispose()` runs, this widget's element may already be
  // deactivated, and reading a provider through it then throws ("Cannot use
  // 'ref' after the widget was disposed"). A `StateController` is a plain
  // Dart object with no widget-lifecycle ties, so holding onto it is safe to
  // call from anywhere, anytime.
  late final StateController<ScopedChapterIdentity?> _openChapterNotifier =
      ref.read(currentlyOpenChapterProvider.notifier);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _claim());
  }

  @override
  void didUpdateWidget(covariant OpenChapterScope oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.chapterId != widget.chapterId) {
      _releaseAsync(_claimed);
      _claimed = null;
      WidgetsBinding.instance.addPostFrameCallback((_) => _claim());
    }
  }

  void _claim() {
    if (!mounted) return;
    final scopeId = ref.read(activeDownloadsScopeIdProvider);
    if (scopeId == null) return;
    final claim = (scopeId: scopeId, id: widget.chapterId);
    _claimed = claim;
    _openChapterNotifier.state = claim;
    unawaited(ref.read(downloadsStoreProvider)?.clearReadStamp(widget.chapterId));
  }

  /// Clears [currentlyOpenChapterProvider] if it still points at [claim] —
  /// deferred to a microtask rather than run synchronously, because a
  /// provider may not be modified from inside a widget lifecycle method
  /// (`dispose`, `didUpdateWidget`, …), which is exactly where every caller
  /// of this lives.
  void _releaseAsync(ScopedChapterIdentity? claim) {
    if (claim == null) return;
    scheduleMicrotask(() {
      if (_openChapterNotifier.state == claim) {
        _openChapterNotifier.state = null;
      }
    });
  }

  @override
  void dispose() {
    _releaseAsync(_claimed);
    _claimed = null;
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
