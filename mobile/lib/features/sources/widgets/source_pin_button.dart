import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/sources/providers/source_pins_provider.dart';

/// The one place pinning happens.
///
/// Pinning used to be a hidden long-press on a grid tile; it is now a real
/// 44x44 target with its own icon state, and the write goes to the server so
/// the pin follows the account instead of the handset.
class SourcePinButton extends ConsumerWidget {
  const SourcePinButton({
    super.key,
    required this.sourceId,
    required this.sourceName,
    this.iconUrl,
    this.mature = false,
    this.iconSize = 20,
  });

  final String sourceId;
  final String sourceName;
  final String? iconUrl;
  final bool mature;
  final double iconSize;

  Future<void> _toggle(BuildContext context, WidgetRef ref) async {
    final messenger = ScaffoldMessenger.of(context);
    // Captured before the await: the palette must not be read from a
    // BuildContext across an async gap.
    final dangerColor = context.colors.danger;
    final wasPinned = ref.read(pinnedSourceIdsProvider).contains(sourceId);
    try {
      await ref.read(sourcePinsProvider.notifier).toggle(
            sourceId,
            name: sourceName,
            iconUrl: iconUrl,
            mature: mature,
          );
      messenger.showSnackBar(
        SnackBar(
          content: Text(
            wasPinned ? '$sourceName unpinned' : '$sourceName pinned',
          ),
          duration: const Duration(seconds: 2),
        ),
      );
    } on AppError catch (error) {
      messenger.showSnackBar(
        SnackBar(
          content: Text(error.userMessage),
          backgroundColor: dangerColor,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isPinned = ref.watch(
      pinnedSourceIdsProvider.select((ids) => ids.contains(sourceId)),
    );

    return IconButton(
      onPressed: () => _toggle(context, ref),
      constraints: const BoxConstraints(minWidth: 44, minHeight: 44),
      padding: EdgeInsets.zero,
      visualDensity: VisualDensity.compact,
      tooltip: isPinned ? 'Unpin $sourceName' : 'Pin $sourceName',
      icon: Icon(
        isPinned ? Icons.push_pin : Icons.push_pin_outlined,
        size: iconSize,
        color: isPinned ? context.colors.primary : context.colors.muted,
      ),
    );
  }
}
