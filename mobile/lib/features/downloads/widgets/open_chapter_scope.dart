import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/downloads/models/chapter_identity.dart';
import 'package:manhwamaniacs/features/downloads/providers/currently_open_chapter_provider.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/services/retention_maintenance.dart'
    show ScopedChapterIdentity;

/// Marks every chapter this reader has on screen as "currently open" for as
/// long as this widget is in the tree — wraps all three reader entry points
/// (the manifest-driven library reader, the online source reader and the
/// novel reader) so the retention sweep and cap eviction can never delete a
/// chapter someone is actively reading, no matter how expired its timer or
/// how tight the storage pressure.
///
/// [chapterId] alone is not the answer for the continuous readers: their
/// feed holds a window of chapters and a Read-all run SLIDES it, so the
/// route's chapter can be three chapters behind what is on screen. Those
/// screens pass the window in [feedChapterIds] and republish it on every
/// slide; a single-chapter reader passes nothing and claims just its route.
///
/// Also clears the read-then-expire stamp of each chapter as it ENTERS the
/// claim: "re-reading cancels it" (spec §3) — a chapter finished long enough
/// ago to be due for deletion must not vanish out from under a deliberate
/// re-read, and in a re-read of a finished series that is every neighbour
/// the window pulls in, not only the one the route opened at. A no-op when
/// there is no active scope, or when a chapter was never downloaded (nothing
/// to protect or un-stamp in either case).
class OpenChapterScope extends ConsumerStatefulWidget {
  const OpenChapterScope({
    super.key,
    required this.chapterId,
    this.feedChapterIds = const [],
    required this.child,
  });

  final ChapterIdentity chapterId;

  /// The chapters the reader's feed is holding right now, when the caller
  /// has a feed at all. Empty for a reader that shows one chapter at a time.
  final List<ChapterIdentity> feedChapterIds;

  final Widget child;

  /// The route's chapter plus the window — what this scope protects. The
  /// route's own chapter stays in even once the window has slid off it: it
  /// is where the reader lands if anything rebuilds them, and one extra
  /// protected row costs nothing.
  Set<ChapterIdentity> get openChapterIds => {chapterId, ...feedChapterIds};

  @override
  ConsumerState<OpenChapterScope> createState() => _OpenChapterScopeState();
}

class _OpenChapterScopeState extends ConsumerState<OpenChapterScope> {
  /// The exact set object last published, compared by IDENTITY on release:
  /// it answers "is this still our claim" rather than "does it look like
  /// ours", so a reader tearing down cannot unprotect the reader that has
  /// already replaced it.
  Set<ScopedChapterIdentity>? _claimed;

  /// Chapters whose expiry timer this scope has already cancelled. A window
  /// that slides back and forth over the same chapter re-publishes the claim
  /// each time; the row only needs writing the first time.
  final Set<ChapterIdentity> _unstamped = {};

  // Resolved once and reused rather than a fresh `ref.read(...)` later: by
  // the time `dispose()` runs, this widget's element may already be
  // deactivated, and reading a provider through it then throws ("Cannot use
  // 'ref' after the widget was disposed"). A `StateController` is a plain
  // Dart object with no widget-lifecycle ties, so holding onto it is safe to
  // call from anywhere, anytime.
  late final StateController<Set<ScopedChapterIdentity>> _openChaptersNotifier =
      ref.read(currentlyOpenChaptersProvider.notifier);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _claim());
  }

  @override
  void didUpdateWidget(covariant OpenChapterScope oldWidget) {
    super.didUpdateWidget(oldWidget);
    // Not released-then-reclaimed: [_claim] replaces the whole set, so there
    // is never a frame in which a sweep would find the window unclaimed.
    if (!setEquals(oldWidget.openChapterIds, widget.openChapterIds)) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _claim());
    }
  }

  void _claim() {
    if (!mounted) return;
    final scopeId = ref.read(activeDownloadsScopeIdProvider);
    if (scopeId == null) return;
    final ids = widget.openChapterIds;
    final claim = {for (final id in ids) (scopeId: scopeId, id: id)};
    _claimed = claim;
    _openChaptersNotifier.state = claim;

    final store = ref.read(downloadsStoreProvider);
    if (store == null) return;
    for (final id in ids) {
      if (_unstamped.add(id)) unawaited(store.clearReadStamp(id));
    }
  }

  /// Empties [currentlyOpenChaptersProvider] if it still holds [claim] —
  /// deferred to a microtask rather than run synchronously, because a
  /// provider may not be modified from inside a widget lifecycle method
  /// (`dispose`, `didUpdateWidget`, …), which is exactly where every caller
  /// of this lives.
  void _releaseAsync(Set<ScopedChapterIdentity>? claim) {
    if (claim == null) return;
    scheduleMicrotask(() {
      if (identical(_openChaptersNotifier.state, claim)) {
        _openChaptersNotifier.state = const {};
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
