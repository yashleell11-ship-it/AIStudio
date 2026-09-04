import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/features/sources/models/source.dart';
import 'package:manhwamaniacs/features/sources/utils/source_branding.dart';
import 'package:manhwamaniacs/features/sources/widgets/source_pin_button.dart';
import 'package:manhwamaniacs/shared/widgets/pressable.dart';
import 'package:manhwamaniacs/shared/widgets/skeleton_box.dart';

/// One source as a full-width row.
///
/// Replaces the old favicon grid: the logo renders at its design size (44)
/// instead of a 16-32px favicon upscaled to 60, the name is body type at a
/// readable size instead of 12px display type, and it never truncates to two
/// cramped lines.
class SourceRowCard extends StatelessWidget {
  const SourceRowCard({
    super.key,
    required this.source,
    required this.onTap,
    this.unavailable = false,
  });

  final SourceSummary source;

  /// Null (or [unavailable]) leaves the row inert — a pin whose connector no
  /// longer resolves is still listed so it can be unpinned, but not opened.
  final VoidCallback? onTap;
  final bool unavailable;

  /// Matches [SourceLogo]'s own default; declared here so the row skeleton
  /// reserves exactly the space the loaded row will use.
  static const double logoSize = 44;

  @override
  Widget build(BuildContext context) {
    final subtitle =
        unavailable ? 'Unavailable on this profile' : source.description.trim();

    return Pressable(
      onTap: unavailable ? null : onTap,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: context.colors.surface,
          borderRadius: BorderRadius.circular(context.radii.lg),
          border: Border.all(color: context.colors.border),
        ),
        child: Padding(
          padding: EdgeInsets.fromLTRB(
            context.space.md,
            context.space.sm,
            context.space.xs,
            context.space.sm,
          ),
          child: Row(
            children: [
              // Only the identity dims when the source is unreachable — the pin
              // button stays at full contrast so the stale pin can be cleared.
              Opacity(
                opacity: unavailable ? 0.55 : 1,
                child: SourceLogo(
                  id: source.id,
                  name: source.name,
                  iconUrl: source.iconUrl,
                ),
              ),
              SizedBox(width: context.space.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Row(
                      children: [
                        Flexible(
                          child: Text(
                            source.name,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: context.text.bodyLg.copyWith(
                              fontWeight: FontWeight.w600,
                              color: unavailable
                                  ? context.colors.muted
                                  : context.colors.fg,
                            ),
                          ),
                        ),
                        if (source.mature) ...[
                          SizedBox(width: context.space.sm),
                          const _MatureBadge(),
                        ],
                      ],
                    ),
                    if (subtitle.isNotEmpty) ...[
                      const SizedBox(height: 2),
                      Text(
                        subtitle,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: context.text.bodySm.copyWith(
                          color: context.colors.muted,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              SizedBox(width: context.space.sm),
              SourcePinButton(
                sourceId: source.id,
                sourceName: source.name,
                iconUrl: source.iconUrl,
                mature: source.mature,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _MatureBadge extends StatelessWidget {
  const _MatureBadge();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(horizontal: context.space.sm, vertical: 1),
      decoration: BoxDecoration(
        color: context.colors.danger.withAlpha(28),
        borderRadius: BorderRadius.circular(context.radii.sm),
        border: Border.all(color: context.colors.danger.withAlpha(90)),
      ),
      child: Text(
        '18+',
        style: context.text.labelSm.copyWith(
          color: context.colors.danger,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}

/// Row-shaped loading placeholder, so the skeleton matches the list it becomes.
class SourceRowSkeleton extends StatelessWidget {
  const SourceRowSkeleton({super.key});

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: context.colors.surface,
        borderRadius: BorderRadius.circular(context.radii.lg),
        border: Border.all(color: context.colors.border),
      ),
      child: Padding(
        padding: EdgeInsets.symmetric(
          horizontal: context.space.md,
          vertical: context.space.md,
        ),
        child: Row(
          children: [
            const SkeletonBox(
              width: SourceRowCard.logoSize,
              height: SourceRowCard.logoSize,
            ),
            SizedBox(width: context.space.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const SkeletonBox(width: 140, height: 14),
                  SizedBox(height: context.space.sm),
                  const SkeletonBox(width: 90, height: 10),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
