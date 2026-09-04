import 'package:flutter/material.dart';
import 'package:manhwamaniacs/features/reader/models/reader_feed.dart';
import 'package:manhwamaniacs/features/reader/theme/reader_colors.dart';

/// The quiet divider between two chapters read in one continuous scroll
/// (spec R1: "a quiet divider names the chapter you are entering without
/// stopping the scroll").
///
/// Deliberately small, deliberately not interactive, and deliberately not an
/// end-of-chapter card: it is a caption passed on the way through, sized to
/// exactly [kChapterSeamExtent] because the page geometry reserved that much
/// and nothing else. Anything with a button on it would be a transition
/// again — the thing the owner asked to stop happening.
///
/// Painted in the reader's own obsidian palette rather than app theme tokens,
/// for the reason `ReaderColors` exists: this sits between two pages of
/// artwork and must not flash a themed frame between them.
class ChapterSeam extends StatelessWidget {
  const ChapterSeam({super.key, required this.title, this.axis = Axis.vertical});

  /// The chapter being entered — the one thing the divider is for.
  final String title;

  /// Horizontal in paged reading, where the seam is a column between two
  /// pages rather than a band across the strip.
  final Axis axis;

  @override
  Widget build(BuildContext context) {
    final label = Text(
      title,
      key: const Key('chapter-seam-title'),
      maxLines: 2,
      textAlign: TextAlign.center,
      overflow: TextOverflow.ellipsis,
      style: const TextStyle(
        fontSize: 12,
        letterSpacing: 1.6,
        fontWeight: FontWeight.w600,
        color: ReaderColors.muted,
      ),
    );

    if (axis == Axis.horizontal) {
      return ColoredBox(
        color: ReaderColors.bg,
        child: Center(
          child: RotatedBox(quarterTurns: 3, child: label),
        ),
      );
    }

    return ColoredBox(
      color: ReaderColors.bg,
      child: Center(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Expanded(child: _Rule()),
              Flexible(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 14),
                  child: label,
                ),
              ),
              const Expanded(child: _Rule()),
            ],
          ),
        ),
      ),
    );
  }
}

class _Rule extends StatelessWidget {
  const _Rule();

  @override
  Widget build(BuildContext context) => Container(
        height: 1,
        constraints: const BoxConstraints(maxWidth: 64),
        color: ReaderColors.muted.withAlpha(60),
      );
}
