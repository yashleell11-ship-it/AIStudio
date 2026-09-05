import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/features/settings/models/reader_defaults.dart';
import 'package:manhwamaniacs/features/settings/providers/settings_provider.dart';

/// Order the actions read left-to-right the way they act: back, stay, forward.
/// Same order and the same words as the web reader's picker, so the two clients
/// describe one setting identically.
const List<TapZoneAction> _tapZoneOptions = [
  TapZoneAction.retreat,
  TapZoneAction.toggle,
  TapZoneAction.advance,
];

/// Left / centre / right tap-action pickers.
///
/// Shared by the reader's own sheet and the Settings screen: both already show
/// the same reader defaults, and one stored config edited from two places beats
/// two surfaces that can disagree.
class TapZonePicker extends ConsumerWidget {
  const TapZonePicker({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final defaults = ref.watch(readerDefaultsProvider);
    final notifier = ref.read(readerDefaultsProvider.notifier);
    final zones =
        defaults.tapZones ?? TapZoneConfig.defaultFor(defaults.direction);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Text('Tap zones', style: context.text.labelLg),
            const Spacer(),
            // Only offered once there is something to undo — the default is
            // already what "reset" would produce.
            if (defaults.tapZones != null)
              TextButton(
                onPressed: () => notifier.setTapZones(null),
                child: const Text('Reset'),
              ),
          ],
        ),
        Padding(
          padding: EdgeInsets.only(bottom: context.space.sm),
          child: Text(
            'What each side of the page does when tapped. Mirrors '
            'automatically for a right-to-left series until you set your own.',
            style: context.text.bodySm.copyWith(color: context.colors.muted),
          ),
        ),
        _TapZoneRow(
          label: 'Left',
          value: zones.left,
          onChanged: (action) =>
              notifier.setTapZones(zones.copyWith(left: action)),
        ),
        _TapZoneRow(
          label: 'Center',
          value: zones.center,
          onChanged: (action) =>
              notifier.setTapZones(zones.copyWith(center: action)),
        ),
        _TapZoneRow(
          label: 'Right',
          value: zones.right,
          onChanged: (action) =>
              notifier.setTapZones(zones.copyWith(right: action)),
        ),
      ],
    );
  }
}

class _TapZoneRow extends StatelessWidget {
  const _TapZoneRow({
    required this.label,
    required this.value,
    required this.onChanged,
  });

  final String label;
  final TapZoneAction value;
  final ValueChanged<TapZoneAction> onChanged;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(bottom: context.space.xs),
      child: Row(
        children: [
          SizedBox(
            width: 56,
            child: Text(
              label,
              style: context.text.bodySm.copyWith(color: context.colors.muted),
            ),
          ),
          Expanded(
            child: SegmentedButton<TapZoneAction>(
              segments: _tapZoneOptions
                  .map(
                    (action) => ButtonSegment(
                      value: action,
                      label: Text(
                        action.label,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  )
                  .toList(),
              selected: {value},
              showSelectedIcon: false,
              onSelectionChanged: (selection) => onChanged(selection.first),
            ),
          ),
        ],
      ),
    );
  }
}
