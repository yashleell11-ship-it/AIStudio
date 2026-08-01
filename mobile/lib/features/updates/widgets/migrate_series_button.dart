import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/updates/providers/updates_provider.dart';
import 'package:manhwamaniacs/features/updates/widgets/migrate_series_sheet.dart';

/// "Move to another source", shown only for a series this profile follows.
///
/// A separate `ConsumerWidget` for the same reason [SeriesFollowButton] is: the
/// series detail screen deliberately does not watch [updatesProvider], so
/// scoping the watch to this button keeps a tracker refresh from rebuilding the
/// whole page and its chapter list.
///
/// Only `followed` trackers can migrate -- a downloaded copy stays with the
/// source its files came from -- and [UpdatesNotifier.trackerFor] already
/// filters to that, so a null tracker is exactly the "cannot migrate" case.
class MigrateSeriesButton extends ConsumerWidget {
  const MigrateSeriesButton({
    required this.sourceId,
    required this.seriesId,
    super.key,
  });

  final String sourceId;
  final String seriesId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.watch(updatesProvider);
    final tracker = ref
        .read(updatesProvider.notifier)
        .trackerFor(source: sourceId, seriesId: seriesId);

    if (tracker == null) return const SizedBox.shrink();

    return OutlinedButton.icon(
      key: const Key('migrate-series'),
      onPressed: () => showMigrateSeriesSheet(context, tracker: tracker),
      icon: const Icon(Icons.swap_horiz_outlined),
      label: const Text('Move Source'),
    );
  }
}
