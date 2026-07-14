import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/features/library/models/continue_reading_item.dart';
import 'package:manhwamaniacs/shared/widgets/premium/fade_in.dart';
import 'package:manhwamaniacs/shared/widgets/premium/glass_panel.dart';
import 'package:manhwamaniacs/shared/widgets/premium/hero_heading.dart';
import 'package:manhwamaniacs/shared/widgets/premium/magnet.dart';
import 'package:manhwamaniacs/shared/widgets/premium/primary_pill_button.dart';
import 'package:manhwamaniacs/shared/widgets/pressable.dart';
import 'package:manhwamaniacs/shared/widgets/series_cover_image.dart';

/// Hero block: big bronze→cream heading, a Magnet-pulled continue-reading
/// cover, an uppercase muted tagline, and the primary "Continue Reading" CTA.
class HomeHero extends StatelessWidget {
  const HomeHero({
    super.key,
    required this.heading,
    required this.tagline,
    required this.coverUrl,
    required this.ctaLabel,
    required this.ctaIcon,
    required this.onCta,
  });

  final String heading;
  final String tagline;

  /// Resolved (auth-gated) cover URL for the resume target, or null for the
  /// placeholder when there is nothing to continue.
  final String? coverUrl;

  final String ctaLabel;
  final IconData ctaIcon;
  final VoidCallback onCta;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xl2),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          HeroHeading(text: heading),
          const SizedBox(height: AppSpacing.xl2),
          Center(
            child: Magnet(
              child: _HeroCover(coverUrl: coverUrl),
            ),
          ),
          const SizedBox(height: AppSpacing.xl2),
          Text(
            tagline.toUpperCase(),
            style: AppTypography.labelSm.copyWith(
              color: AppColors.muted,
              letterSpacing: 2.4,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: AppSpacing.lg),
          Align(
            alignment: Alignment.centerLeft,
            child: PrimaryPillButton(
              label: ctaLabel,
              icon: ctaIcon,
              onPressed: onCta,
            ),
          ),
        ],
      ),
    );
  }
}

class _HeroCover extends StatelessWidget {
  const _HeroCover({required this.coverUrl});

  final String? coverUrl;

  @override
  Widget build(BuildContext context) {
    const width = 168.0;
    const height = 252.0; // 2 : 3 portrait

    final child = coverUrl != null
        ? SeriesCoverImage(
            url: coverUrl!,
            width: width,
            height: height,
            borderRadius: AppRadius.xl2,
          )
        : DecoratedBox(
            decoration: BoxDecoration(
              color: AppColors.surface2,
              borderRadius: BorderRadius.circular(AppRadius.xl2),
              border: Border.all(color: AppColors.border),
            ),
            child: Center(
              child: Icon(
                Icons.auto_stories_outlined,
                size: 44,
                color: AppColors.muted.withValues(alpha: 0.55),
              ),
            ),
          );

    return Container(
      width: width,
      height: height,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(AppRadius.xl2),
        boxShadow: [
          BoxShadow(
            color: AppColors.primary.withValues(alpha: 0.22),
            blurRadius: 40,
            spreadRadius: -8,
            offset: const Offset(0, 16),
          ),
        ],
      ),
      child: child,
    );
  }
}

/// "About" block — a frosted glass panel that fades in with a short blurb and a
/// warm CTA.
class HomeAbout extends StatelessWidget {
  const HomeAbout({
    super.key,
    required this.onCta,
  });

  final VoidCallback onCta;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xl2),
      child: FadeIn(
        child: GlassPanel(
          padding: const EdgeInsets.all(AppSpacing.xl2),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'ABOUT',
                style: AppTypography.labelSm.copyWith(
                  color: AppColors.primary,
                  letterSpacing: 3,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              Text(
                'Every series you follow, in one warm, quiet place. '
                'Track new chapters, pick up mid-page, and read offline whenever '
                'the mood strikes.',
                style: AppTypography.body.copyWith(
                  color: AppColors.fg,
                  height: 1.5,
                ),
              ),
              const SizedBox(height: AppSpacing.xl),
              PrimaryPillButton(
                label: 'Browse Sources',
                icon: Icons.travel_explore_rounded,
                onPressed: onCta,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// A single tappable card in the "Continue" list — cover + title + optional
/// chapter subtitle and progress bar.
class HomeContinueCard extends StatelessWidget {
  const HomeContinueCard({
    super.key,
    required this.coverUrl,
    required this.title,
    required this.subtitle,
    required this.onTap,
    this.progressPct,
  });

  /// Resolved (auth-gated) cover URL.
  final String coverUrl;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  /// 0–100 reading progress; null hides the progress bar.
  final double? progressPct;

  @override
  Widget build(BuildContext context) {
    return Pressable(
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(AppRadius.xl),
          border: Border.all(color: AppColors.border),
        ),
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Row(
          children: [
            SeriesCoverImage(
              url: coverUrl,
              width: 56,
              height: 78,
            ),
            const SizedBox(width: AppSpacing.lg),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(
                    title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: AppTypography.labelLg
                        .copyWith(fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: AppSpacing.xxs),
                  Text(
                    subtitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: AppTypography.caption.copyWith(color: AppColors.muted),
                  ),
                  if (progressPct != null) ...[
                    const SizedBox(height: AppSpacing.sm),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(AppRadius.pill),
                      child: LinearProgressIndicator(
                        value: (progressPct! / 100).clamp(0.0, 1.0),
                        minHeight: 3,
                        backgroundColor: AppColors.fg.withValues(alpha: 0.08),
                        color: AppColors.primary,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            const Icon(
              Icons.play_arrow_rounded,
              color: AppColors.primary,
              size: 24,
            ),
          ],
        ),
      ),
    );
  }
}

/// Builds the resume subtitle for a continue-reading item.
String continueSubtitle(ContinueReadingItem item) =>
    '${item.chapterTitle}  ·  ${item.progressPct.round()}%';

/// Small uppercase section label used above home lists.
class HomeSectionLabel extends StatelessWidget {
  const HomeSectionLabel({super.key, required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xl2),
      child: Text(
        text.toUpperCase(),
        style: AppTypography.label.copyWith(
          color: AppColors.fg,
          letterSpacing: 2,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}
