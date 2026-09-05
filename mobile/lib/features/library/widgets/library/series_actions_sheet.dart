import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/features/library/models/followed_series.dart';
import 'package:manhwamaniacs/features/library/providers/library_series_actions.dart';
import 'package:manhwamaniacs/features/profiles/providers/profile_scope.dart';

/// The long-press menu for one followed series, and everything behind its
/// destructive row.
///
/// Written once for both shelves — the Library tab and the browse screen under
/// it show the same follows, and a delete that deliberately has no
/// confirmation step is exactly the thing that must not exist twice: two
/// copies is how one screen quietly grows a dialog and the other does not.
///
/// [onOpen] is the one part the two surfaces genuinely disagree on. The Library
/// tab opens a series by `(source, series key)` and the browse screen opens it
/// by follow-row id, because they route to different pages.
Future<void> showSeriesActionsSheet(
  BuildContext context,
  WidgetRef ref,
  FollowedSeries series, {
  required VoidCallback onOpen,
}) {
  return showModalBottomSheet<void>(
    context: context,
    showDragHandle: true,
    builder: (sheetCtx) => SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Padding(
            padding: EdgeInsets.fromLTRB(
              sheetCtx.space.xl2,
              0,
              sheetCtx.space.xl2,
              sheetCtx.space.sm,
            ),
            child: Text(
              series.title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: sheetCtx.text.h4,
            ),
          ),
          ListTile(
            leading: const Icon(Icons.open_in_new),
            title: const Text('Open'),
            onTap: () {
              Navigator.pop(sheetCtx);
              onOpen();
            },
          ),
          ListTile(
            leading: Icon(
              series.isFavorite ? Icons.star : Icons.star_border,
              color: series.isFavorite ? sheetCtx.colors.warning : null,
            ),
            title: Text(
              series.isFavorite ? 'Remove from favorites' : 'Add to favorites',
            ),
            onTap: () {
              Navigator.pop(sheetCtx);
              unawaited(_toggleFavorite(context, ref, series));
            },
          ),
          const Divider(height: 1),
          // Last, and behind a divider: the sheet opens under the thumb that
          // long-pressed the card, and the destructive row is the one that
          // must not sit where a stray second tap lands.
          ListTile(
            leading: Icon(
              Icons.remove_circle_outline,
              color: sheetCtx.colors.danger,
            ),
            title: Text(
              'Remove from library',
              style: TextStyle(color: sheetCtx.colors.danger),
            ),
            subtitle: const Text('Your reading progress is kept'),
            onTap: () {
              Navigator.pop(sheetCtx);
              unawaited(_removeFromLibrary(context, ref, series));
            },
          ),
          SizedBox(height: sheetCtx.space.sm),
        ],
      ),
    ),
  );
}

Future<void> _toggleFavorite(
  BuildContext context,
  WidgetRef ref,
  FollowedSeries series,
) async {
  final messenger = ScaffoldMessenger.of(context);
  final error = await ref
      .read(librarySeriesActionsProvider)
      .setFavorite(series, favorite: !series.isFavorite);
  if (!context.mounted || error == null) return;
  if (recoverFromProfileScopeError(ref, error)) return;
  messenger.showSnackBar(SnackBar(content: Text(error.userMessage)));
}

/// Unfollows [series] straight from the shelf.
///
/// No confirmation step: the row that goes is the follow, and reading
/// progress is keyed by source + series and survives it, so the whole cost
/// of a mis-tap is one re-follow. A dialog would put back the taps this
/// menu exists to remove; an Undo in the snackbar buys the same safety
/// without charging for it every time the removal was intended.
Future<void> _removeFromLibrary(
  BuildContext context,
  WidgetRef ref,
  FollowedSeries series,
) async {
  final messenger = ScaffoldMessenger.of(context);
  final outcome = await ref.read(librarySeriesActionsProvider).remove(series);
  if (!context.mounted) return;

  final error = outcome.error;
  if (error != null) {
    // The card is already back on the shelf; say why it never left.
    if (recoverFromProfileScopeError(ref, error)) return;
    messenger.showSnackBar(SnackBar(content: Text(error.userMessage)));
    return;
  }

  messenger
    ..hideCurrentSnackBar()
    ..showSnackBar(
      SnackBar(
        content: Text(
          'Removed \u201c${series.title}\u201d from your library',
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
        ),
        action: SnackBarAction(
          label: 'Undo',
          onPressed: () => unawaited(
            _restoreToLibrary(context, ref, series, outcome.slots),
          ),
        ),
      ),
    );
}

Future<void> _restoreToLibrary(
  BuildContext context,
  WidgetRef ref,
  FollowedSeries series,
  ShelfSlots slots,
) async {
  // The snackbar outlives the screen that raised it, so the Undo can be
  // tapped after this ref's widget is gone.
  if (!context.mounted) return;
  final messenger = ScaffoldMessenger.of(context);
  final error = await ref
      .read(librarySeriesActionsProvider)
      .restore(series, slots: slots);
  if (!context.mounted || error == null) return;
  if (recoverFromProfileScopeError(ref, error)) return;
  messenger.showSnackBar(SnackBar(content: Text(error.userMessage)));
}
