import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';

/// "Read all" — the second entry point on a series page (spec R2), in the
/// owner's words: "there should be a small clickable button when i click a
/// manhwa there is read online there should be one for read all and ofc read
/// online for as usual".
///
/// Beside the primary read action rather than in a settings menu or a mode
/// toggle: it is a *way of starting to read this series*, and the moment it is
/// wanted is the moment the reader is looking at Read online and deciding.
///
/// Deliberately secondary in weight. Read online stays the button the eye
/// lands on — Read all is the one you go looking for.
class ReadAllButton extends StatelessWidget {
  const ReadAllButton({super.key, required this.onPressed});

  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: 'Read the whole series as one continuous scroll',
      child: OutlinedButton.icon(
        key: const Key('read-all'),
        onPressed: onPressed,
        icon: const Icon(Icons.all_inclusive_rounded, size: 18),
        label: const Text('Read all'),
        style: OutlinedButton.styleFrom(
          foregroundColor: context.colors.fg,
          side: BorderSide(color: context.colors.border),
          backgroundColor: context.colors.fg.withAlpha(13),
          padding: EdgeInsets.symmetric(
            horizontal: context.space.lg,
            vertical: context.space.md,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(context.radii.pill),
          ),
        ),
      ),
    );
  }
}
